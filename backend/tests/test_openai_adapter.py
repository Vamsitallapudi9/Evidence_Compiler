"""OpenAI adapter request/response handling, against a mocked HTTP transport."""

import json
from dataclasses import replace

import httpx
import openai
import pytest

from evidence_compiler.config import Settings
from evidence_compiler.llm.base import LLMError, LLMRefusal
from evidence_compiler.llm.openai_client import OpenAIClient
from evidence_compiler.pipeline.schemas import ClaimDraft, Entailment

SETTINGS = replace(
    Settings(), llm_provider="openai", strong_model="gpt-6-luna", fast_model="gpt-6-luna"
)


def make(responder, settings=SETTINGS):
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        return responder(body)

    client = openai.OpenAI(
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    return OpenAIClient(settings, client), seen


def response(content: list[dict], status: str = "completed", incomplete=None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "model": "gpt-6-luna",
            "status": status,
            "incomplete_details": incomplete,
            "output": [
                {
                    "type": "message",
                    "id": "m1",
                    "role": "assistant",
                    "status": "completed",
                    "content": content,
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        },
    )


def text(t: str) -> list[dict]:
    return [{"type": "output_text", "text": t, "annotations": []}]


def test_sends_strict_json_schema_and_parses():
    llm, seen = make(lambda b: response(text('{"verdict": "supports", "note": "ok"}')))
    out = llm.generate(task="verify", system="sys", prompt="p", schema=Entailment)
    assert out == Entailment(verdict="supports", note="ok")
    body = seen[0]
    assert body["model"] == "gpt-6-luna"
    assert body["instructions"] == "sys"
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert "reasoning" not in body


def test_nested_schema_with_optional_fields_is_accepted():
    draft = {
        "claims": [
            {
                "text": "x",
                "claim_type": "primary",
                "citations": [{"evidence_id": "e1", "quote": None}],
                "calculation": None,
            }
        ],
        "hypotheses": [],
        "gaps": [],
    }
    llm, seen = make(lambda b: response(text(json.dumps(draft))))
    out = llm.generate(task="claims", system="s", prompt="p", schema=ClaimDraft)
    assert out.claims[0].citations[0].evidence_id == "e1"
    assert seen[0]["text"]["format"]["schema"]["additionalProperties"] is False


def test_reasoning_effort_is_optional():
    llm, seen = make(
        lambda b: response(text('{"verdict": "partial", "note": "x"}')),
        replace(SETTINGS, openai_reasoning_effort="low"),
    )
    llm.generate(task="t", system="s", prompt="p", schema=Entailment)
    assert seen[0]["reasoning"] == {"effort": "low"}


def test_refusal_incomplete_and_errors():
    llm, _ = make(lambda b: response([{"type": "refusal", "refusal": "no"}]))
    with pytest.raises(LLMRefusal):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)
    llm, _ = make(
        lambda b: response([], status="incomplete", incomplete={"reason": "max_output_tokens"})
    )
    with pytest.raises(LLMError, match="incomplete"):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)
    llm, _ = make(lambda b: httpx.Response(404, json={"error": {"message": "no such model"}}))
    with pytest.raises(LLMError, match="not found"):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)
    llm, _ = make(lambda b: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(LLMError, match="API key"):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)


def test_provider_defaults(monkeypatch):
    monkeypatch.setenv("EC_LLM_PROVIDER", "openai")
    monkeypatch.delenv("EC_STRONG_MODEL", raising=False)
    monkeypatch.delenv("EC_FAST_MODEL", raising=False)
    s = Settings()
    assert (s.llm_provider, s.strong_model, s.fast_model) == ("openai", "gpt-6-luna", "gpt-6-luna")
    from evidence_compiler.llm import make_llm

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert make_llm(s).name == "openai"
