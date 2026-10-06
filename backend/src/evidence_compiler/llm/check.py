"""Verify the configured LLM end to end:  python -m evidence_compiler.llm.check

Confirms the API key works, the configured model IDs exist for this key, and a tiny
structured-output request succeeds. Costs a fraction of a cent.
"""

import sys

from evidence_compiler.config import get_settings
from evidence_compiler.llm import LLMError, llm_configured, make_llm
from evidence_compiler.pipeline.schemas import Entailment


def _list_models(provider: str) -> list[str] | None:
    try:
        if provider == "openai":
            import openai

            return sorted(m.id for m in openai.OpenAI().models.list())
        import anthropic

        return sorted(m.id for m in anthropic.Anthropic().models.list())
    except Exception as exc:  # report and carry on to the generation test
        print(f"  could not list models: {exc}")
        return None


def main() -> int:
    s = get_settings()
    print(f"provider: {s.llm_provider}\nstrong model: {s.strong_model}\nfast model: {s.fast_model}")
    if not llm_configured(s):
        key = "OPENAI_API_KEY" if s.llm_provider == "openai" else "ANTHROPIC_API_KEY"
        print(f"FAIL: {key} is not set (add it to .env)")
        return 1
    models = _list_models(s.llm_provider)
    if models is not None:
        for m in {s.strong_model, s.fast_model}:
            if m in models:
                print(f"  ok: {m} is available")
            else:
                close = [x for x in models if x.split("-")[0] in m][:15]
                print(f"  WARNING: {m} not in this key's model list. Similar: {', '.join(close)}")
    try:
        out = make_llm(s).generate(
            task="check",
            system="Return verdict 'supports' and note 'ok'.",
            prompt="Claim: 2+2=4. Evidence: 2+2=4.",
            schema=Entailment,
            tier="strong",
        )
    except LLMError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"  ok: structured output works ({out.verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
