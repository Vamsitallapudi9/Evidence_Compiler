"""Claude adapter for the LLMClient interface, using structured outputs."""

import anthropic
import pydantic

from evidence_compiler.config import Settings
from evidence_compiler.llm.base import LLMError, LLMRefusal, T, Tier, Usage

# Models that accept the server-side refusal fallback parameter on the Claude API.
_FALLBACK_MODELS = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5")
_EFFORT_MODELS = ("claude-opus-", "claude-sonnet-", "claude-fable-")


class AnthropicClient:
    name = "anthropic"

    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.settings = settings
        self.client = client or anthropic.Anthropic(
            timeout=settings.llm_timeout_s, max_retries=settings.llm_max_retries
        )

    def model_for(self, tier: Tier) -> str:
        return self.settings.strong_model if tier == "strong" else self.settings.fast_model

    def generate(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> T:
        return self.generate_with_usage(
            task=task, system=system, prompt=prompt, schema=schema, tier=tier
        )[0]

    def generate_with_usage(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> tuple[T, Usage]:
        model = self.model_for(tier)
        kwargs: dict = {
            "model": model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "output_format": schema,
        }
        if tier == "strong" and model.startswith(_EFFORT_MODELS):
            kwargs["output_config"] = {"effort": self.settings.strong_effort}
        try:
            if self.settings.llm_fallbacks and model.startswith(_FALLBACK_MODELS):
                response = self.client.beta.messages.parse(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = self.client.messages.parse(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise LLMError(
                f"{task}: no response from the model within {self.settings.llm_timeout_s:.0f}s"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError(f"{task}: rate limited ({exc.status_code})") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"{task}: API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"{task}: could not reach the Claude API") from exc
        except pydantic.ValidationError as exc:
            raise LLMError(f"{task}: model output was invalid or truncated: {exc}") from exc
        except TypeError as exc:
            if "authentication" not in str(exc).lower():
                raise
            raise LLMError(
                "No Claude API credentials found. Set ANTHROPIC_API_KEY in .env "
                "(see .env.example) and restart the API."
            ) from exc

        if response.stop_reason == "refusal":
            raise LLMRefusal(f"{task}: the model declined this request")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"{task}: output truncated at max_tokens")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError(f"{task}: no structured output returned")
        u = response.usage
        usage = Usage(
            model=getattr(response, "model", None) or model,
            input_tokens=getattr(u, "input_tokens", None),
            output_tokens=getattr(u, "output_tokens", None),
            cached_input_tokens=getattr(u, "cache_read_input_tokens", None),
        )
        return parsed, usage
