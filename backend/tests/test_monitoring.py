"""Live run monitoring: token usage, heartbeats, cancellation, interrupted runs."""

import json
import threading
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from evidence_compiler.api.main import create_app
from evidence_compiler.app import AppContext
from evidence_compiler.core.models import RunStatus
from evidence_compiler.llm.base import LLMError
from evidence_compiler.llm.meter import MeteredLLM, RunCancelled
from evidence_compiler.pipeline.schemas import Entailment, QuestionPlan
from tests.fake_scenario import make_fake


def wait(ctx, run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ctx.runs.status(run_id) in (RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED):
            return ctx.runs.status(run_id)
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_meter_counts_tokens_and_labels(settings):
    fake = make_fake()
    seen = []
    meter = MeteredLLM(
        fake,
        replace(settings, price_input_per_m=1.0, price_output_per_m=4.0),
        on_call=lambda c: seen.append((c.status, c.label)),
    )
    with meter.activity("Verifying claim 2 of 5"):
        meter.generate(task="verify", system="s", prompt="p" * 400, schema=Entailment)
    meter.generate(task="plan", system="s", prompt="p", schema=QuestionPlan)
    assert seen[0] == ("running", "Verifying claim 2 of 5") and seen[1][0] == "ok"
    assert seen[2] == ("running", "Planning the question")
    s = meter.summary(include_log=True)
    assert s["calls"] == 2 and s["in_flight"] == 0 and s["input_tokens"] >= 100
    assert s["est_cost_usd"] is not None and len(s["calls_log"]) == 2


def test_meter_records_failures_and_cancellation(settings):
    def boom(prompt, schema):
        raise LLMError("no response from the model within 180s")

    fake = make_fake()
    fake.handlers["verify"] = boom
    meter = MeteredLLM(fake, settings)
    with pytest.raises(LLMError):
        meter.generate(task="verify", system="s", prompt="p", schema=Entailment)
    assert meter.summary()["failed_calls"] == 1
    meter.cancel.set()
    with pytest.raises(RunCancelled):
        meter.generate(task="verify", system="s", prompt="p", schema=Entailment)


def test_run_records_usage_and_heartbeat(ctx):
    ctx._llm = make_fake()
    run_id = ctx.runs.start("Why did Q2 revenue decline?")
    assert wait(ctx, run_id) == RunStatus.DONE
    usage = ctx.runs.usage(run_id)
    assert usage["calls"] >= 6 and usage["input_tokens"] > 0 and usage["output_tokens"] > 0
    assert {c["task"] for c in usage["calls_log"]} >= {"plan", "sql", "claims", "verify", "compile"}
    assert any(c["label"].startswith("Verifying claim 1 of") for c in usage["calls_log"])
    beat = ctx.runs.heartbeat(run_id)
    assert beat["alive"] is False and beat["usage"]["calls"] == usage["calls"]
    persisted = json.loads(ctx.repo.get_run(run_id).usage)
    assert persisted["input_tokens"] == usage["input_tokens"]


def test_cancel_stops_the_run(ctx):
    gate = threading.Event()
    fake = make_fake()
    original = fake.handlers["claims"]

    def slow_claims(prompt, schema):
        gate.wait(5)
        return original(prompt, schema)

    fake.handlers["claims"] = slow_claims
    ctx._llm = fake
    run_id = ctx.runs.start("Why did Q2 revenue decline?")
    deadline = time.time() + 5
    while not any(c["task"] == "claims" for c in ctx.runs.call_snapshots(run_id)):
        assert time.time() < deadline
        time.sleep(0.02)
    beat = ctx.runs.heartbeat(run_id)
    assert beat["alive"] and beat["current"] == "Drafting claims from the evidence"
    assert beat["usage"]["in_flight"] == 1
    assert ctx.runs.cancel(run_id)
    gate.set()  # let the in-flight call finish; the next step must not start
    assert wait(ctx, run_id) == RunStatus.CANCELLED
    assert not any(c["task"] == "verify" for c in ctx.runs.call_snapshots(run_id))
    assert not ctx.runs.cancel(run_id)


def test_unfinished_runs_are_marked_interrupted_on_restart(settings, demo_dir):
    first = AppContext(settings, llm=make_fake())
    first.repo.create_run("run_orphan", "q")
    first.repo.update_run("run_orphan", status=RunStatus.RUNNING)
    second = AppContext(settings, llm=make_fake())  # simulates a server restart
    row = second.repo.get_run("run_orphan")
    assert row.status == "failed" and row.error.startswith("Interrupted:")
    assert second.runs.alive("run_orphan") is False


def test_api_exposes_usage_cancel_and_live_events(settings, demo_dir):
    ctx = AppContext(settings, llm=make_fake())
    ctx.ingest_file(demo_dir / "q2_fy2026_report.pdf")
    ctx.ingest_file(demo_dir / "regional_sales.csv")
    ctx.ingest_file(demo_dir / "customer_segments.xlsx")
    with TestClient(create_app(ctx)) as client:
        run_id = client.post("/api/runs", json={"question": "Why did Q2 revenue decline?"}).json()[
            "run_id"
        ]
        with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
            body = "".join(stream.iter_text())
        assert "event: llm" in body and "event: heartbeat" in body and "event: done" in body
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["usage"]["calls"] >= 6 and run["usage"]["calls_log"] and run["alive"] is False
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409
        health = client.get("/api/health").json()
        assert "llm_model" in health and "pricing_configured" in health


def test_openai_client_uses_bounded_timeout(settings, monkeypatch):
    from evidence_compiler.llm.openai_client import OpenAIClient

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    client = OpenAIClient(replace(settings, llm_timeout_s=42.0, llm_max_retries=1))
    assert client.client.timeout == 42.0 and client.client.max_retries == 1
