"""Claude adapter request/response handling, against a mocked HTTP transport."""

import json
from dataclasses import replace

import anthropic
import httpx2 as httpx
import pytest

from evidence_compiler.config import Settings
from evidence_compiler.llm.anthropic_client import AnthropicClient
from evidence_compiler.llm.base import LLMError, LLMRefusal
from evidence_compiler.pipeline.schemas import Entailment


def make(responder):
    seen: list[tuple[httpx.Request, dict]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append((req, body))
        return responder(body)

    client = anthropic.Anthropic(
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    settings = replace(
        Settings(),
        llm_provider="anthropic",
        strong_model="claude-opus-5-5",
        fast_model="claude-haiku-4-5",
        strong_effort="medium",
        llm_fallbacks=True,
    )
    return AnthropicClient(settings, client), seen


def message(text: str, stop_reason: str = "end_turn") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}] if text else [],
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )


def test_strong_tier_uses_effort_fallbacks_and_json_schema():
    llm, seen = make(lambda b: message('{"verdict": "supports", "note": "ok"}'))
    out = llm.generate(task="verify", system="s", prompt="p", schema=Entailment, tier="strong")
    assert out == Entailment(verdict="supports", note="ok")
    req, body = seen[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    assert "tool_choice" not in body  # forced tool use is rejected by current models


def test_fast_tier_is_plain_structured_output():
    llm, seen = make(lambda b: message('{"verdict": "partial", "note": "x"}'))
    llm.generate(task="plan", system="s", prompt="p", schema=Entailment, tier="fast")
    _, body = seen[0]
    assert body["model"] == "claude-haiku-4-5"
    assert "fallbacks" not in body and "effort" not in body["output_config"]


def test_refusal_and_truncation_raise():
    llm, _ = make(lambda b: message("", stop_reason="refusal"))
    with pytest.raises(LLMRefusal):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)
    llm, _ = make(lambda b: message('{"verdict": "sup', stop_reason="max_tokens"))
    with pytest.raises(LLMError, match="truncated"):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)


def test_api_errors_become_llm_errors():
    llm, _ = make(
        lambda b: httpx.Response(
            400,
            json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}},
        )
    )
    with pytest.raises(LLMError, match="400"):
        llm.generate(task="t", system="s", prompt="p", schema=Entailment)
