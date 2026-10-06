"""OpenAI adapter for the LLMClient interface (Responses API + structured outputs)."""

import openai
import pydantic

from evidence_compiler.config import Settings
from evidence_compiler.llm.base import LLMError, LLMRefusal, T, Tier, Usage


class OpenAIClient:
    name = "openai"

    def __init__(self, settings: Settings, client: openai.OpenAI | None = None):
        self.settings = settings
        self.client = client or openai.OpenAI(
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
        kwargs: dict = {
            "model": self.model_for(tier),
            "instructions": system,
            "input": [{"role": "user", "content": prompt}],
            "text_format": schema,
            "max_output_tokens": 16000,
        }
        if self.settings.openai_reasoning_effort:
            kwargs["reasoning"] = {"effort": self.settings.openai_reasoning_effort}
        try:
            response = self.client.responses.parse(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMError(
                "OpenAI rejected the API key. Set OPENAI_API_KEY in .env and restart the API."
            ) from exc
        except openai.NotFoundError as exc:
            raise LLMError(
                f"{task}: model '{kwargs['model']}' not found for this API key — set "
                "EC_STRONG_MODEL / EC_FAST_MODEL in .env (run `make check-llm` to list models)"
            ) from exc
        except openai.APITimeoutError as exc:
            raise LLMError(
                f"{task}: no response from the model within {self.settings.llm_timeout_s:.0f}s"
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMError(f"{task}: rate limited or out of credit ({exc.status_code})") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"{task}: API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(f"{task}: could not reach the OpenAI API") from exc
        except pydantic.ValidationError as exc:
            raise LLMError(f"{task}: model output was invalid or truncated: {exc}") from exc
        except openai.OpenAIError as exc:  # e.g. missing API key at client construction
            raise LLMError(f"{task}: {exc}") from exc

        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", "unknown")
            raise LLMError(f"{task}: output incomplete ({reason})")
        for item in response.output:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    raise LLMRefusal(f"{task}: the model declined this request")
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError(f"{task}: no structured output returned")
        u = response.usage
        usage = Usage(
            model=getattr(response, "model", None) or kwargs["model"],
            input_tokens=getattr(u, "input_tokens", None),
            output_tokens=getattr(u, "output_tokens", None),
            reasoning_tokens=getattr(
                getattr(u, "output_tokens_details", None), "reasoning_tokens", None
            ),
            cached_input_tokens=getattr(
                getattr(u, "input_tokens_details", None), "cached_tokens", None
            ),
        )
        return parsed, usage
