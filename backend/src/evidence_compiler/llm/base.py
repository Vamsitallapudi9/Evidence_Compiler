"""Provider-agnostic LLM interface.

The pipeline only ever asks a model for *structured* output validated against a
Pydantic schema. Models reference evidence by ID; they have no path to create it.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

Tier = Literal["fast", "strong"]
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


@dataclass(frozen=True)
class Usage:
    """Token accounting for one model call (None = provider did not report it)."""

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    cached: bool = False  # served from the local response cache, no API call


def generate_with_usage[M: BaseModel](
    llm: "LLMClient", *, task: str, system: str, prompt: str, schema: type[M], tier: Tier
) -> tuple[M, Usage | None]:
    """Call ``llm`` and return usage when the client can report it."""
    fn = getattr(llm, "generate_with_usage", None)
    if fn is not None:
        return fn(task=task, system=system, prompt=prompt, schema=schema, tier=tier)
    return llm.generate(task=task, system=system, prompt=prompt, schema=schema, tier=tier), None


class LLMClient(Protocol):
    name: str

    def generate(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> T:
        """Return an instance of ``schema``. ``task`` labels the call for logs/caching.

        Clients may also implement ``generate_with_usage`` (same arguments) returning
        ``(result, Usage)`` so runs can show live token counts.
        """
        ...
