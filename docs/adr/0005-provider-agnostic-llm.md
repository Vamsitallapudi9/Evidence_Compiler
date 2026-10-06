# ADR 0005: Provider-agnostic LLM interface

**Status:** accepted

**Decision.** The pipeline depends on `LLMClient.generate(task, system, prompt, schema,
tier)` returning a validated Pydantic object. Phase 1 ships a Claude adapter using
structured outputs (`messages.parse`). The defaults are `claude-opus-5-5` (strong tier)
and `claude-haiku-4-5` (fast tier), configurable via env. Forced tool use is not used,
because current Claude models reject it. A `FakeLLM` drives tests and a disk cache
makes evaluations reproducible.

**Update (OpenAI adapter).** `llm/openai_client.py` uses the Responses API with strict
structured outputs (`responses.parse(text_format=...)`). With `EC_LLM_PROVIDER=openai`
both tiers default to `gpt-6-luna`. When only one model is used, the "fast" and
"strong" tiers share it.

**Consequences.** Adding Bedrock or a local model means adding one adapter file.
Prompt behaviour may differ across providers and should be re-evaluated with
`make eval`.
