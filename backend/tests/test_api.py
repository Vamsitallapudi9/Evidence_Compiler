import time

import pytest
from fastapi.testclient import TestClient

from evidence_compiler.api.main import create_app
from evidence_compiler.app import AppContext
from tests.conftest import DEMO_PG_DSN, requires_pg
from tests.fake_scenario import make_fake


@pytest.fixture
def client(settings, demo_dir):
    ctx = AppContext(settings, llm=make_fake())
    with TestClient(create_app(ctx)) as c:
        for name in ["q2_fy2026_report.pdf", "regional_sales.csv", "customer_segments.xlsx"]:
            with open(demo_dir / name, "rb") as f:
                r = c.post("/api/sources", files={"file": (name, f)})
                assert r.status_code == 201, r.text
        yield c


def wait_done(client, run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_sources_listing(client):
    sources = client.get("/api/sources").json()
    by_name = {s["name"]: s for s in sources}
    assert by_name["q2_fy2026_report.pdf"]["evidence_count"] > 5
    assert by_name["q2_fy2026_report.pdf"]["flagged_count"] == 1
    assert by_name["q2_fy2026_report.pdf"]["page_count"] == 3
    assert by_name["regional_sales.csv"]["tables"] == ["regional_sales"]


def test_rejects_unsupported_upload(client):
    r = client.post("/api/sources", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 400


def test_run_lifecycle_and_sse(client):
    run_id = client.post("/api/runs", json={"question": "Why did Q2 revenue decline?"}).json()[
        "run_id"
    ]
    run = wait_done(client, run_id)
    assert run["status"] == "done", run.get("error")
    answer = run["answer"]
    assert answer["claims"] and "[c:" in answer["text"]
    assert answer["graph"]["nodes"]

    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        body = "".join(stream.iter_text())
    assert "event: progress" in body and "event: done" in body

    ev_id = answer["claims"][0]["links"][0]["evidence_id"]
    assert client.get(f"/api/evidence/{ev_id}").status_code == 200
    assert client.get("/api/runs").json()[0]["id"] == run_id


def test_page_text_matches_offsets(client):
    pdf = next(s for s in client.get("/api/sources").json() if s["kind"] == "pdf")
    run_id = client.post("/api/runs", json={"question": "Why did Q2 revenue decline?"}).json()[
        "run_id"
    ]
    answer = wait_done(client, run_id)["answer"]
    pdf_ev = next(e for e in answer["evidence"].values() if e["location"]["kind"] == "pdf")
    loc = pdf_ev["location"]
    page = client.get(f"/api/sources/{pdf['id']}/pages/{loc['page']}").json()
    assert page["text"][loc["char_start"] : loc["char_end"]] == pdf_ev["text"]


def test_delete_source(client):
    csv = next(s for s in client.get("/api/sources").json() if s["kind"] == "csv")
    assert client.delete(f"/api/sources/{csv['id']}").status_code == 204
    assert all(s["id"] != csv["id"] for s in client.get("/api/sources").json())
    assert client.delete(f"/api/sources/{csv['id']}").status_code == 404


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


@requires_pg
def test_register_postgres_hides_password(client):
    r = client.post("/api/sources/postgres", json={"name": "crm", "dsn": DEMO_PG_DSN})
    assert r.status_code == 201, r.text
    assert set(r.json()["tables"]) == {"customers", "contract_events"}
    assert "ec_reader_local_only" not in client.get("/api/sources").text


def test_register_postgres_bad_dsn(client):
    r = client.post(
        "/api/sources/postgres", json={"name": "x", "dsn": "postgresql://nobody@127.0.0.1:1/x"}
    )
    assert r.status_code == 422
