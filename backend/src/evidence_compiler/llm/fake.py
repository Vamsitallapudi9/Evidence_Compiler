"""Deterministic stand-in for tests: responses come from per-task handler functions."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from evidence_compiler.llm.base import LLMError, T, Tier, Usage

Handler = Callable[[str, type[BaseModel]], BaseModel | dict[str, Any]]


@dataclass
class FakeCall:
    task: str
    system: str
    prompt: str
    tier: Tier


@dataclass
class FakeLLM:
    handlers: dict[str, Handler]
    name: str = "fake"

    def model_for(self, tier: Tier) -> str:
        return self.name

    calls: list[FakeCall] = field(default_factory=list)

    def generate(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> T:
        return self.generate_with_usage(
            task=task, system=system, prompt=prompt, schema=schema, tier=tier
        )[0]

    def generate_with_usage(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> tuple[T, Usage]:
        self.calls.append(FakeCall(task, system, prompt, tier))
        handler = self.handlers.get(task)
        if handler is None:
            raise LLMError(f"FakeLLM has no handler for task '{task}'")
        out = handler(prompt, schema)
        result = out if isinstance(out, schema) else schema.model_validate(out)
        # Rough token estimate (4 chars/token) so the UI's counters can be exercised.
        usage = Usage(
            model=self.name,
            input_tokens=(len(system) + len(prompt)) // 4,
            output_tokens=len(result.model_dump_json()) // 4,
        )
        return result, usage
