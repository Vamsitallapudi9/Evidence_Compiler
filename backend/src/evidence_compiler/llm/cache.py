"""Disk cache for LLM calls: reproducible evaluations and lower cost on reruns."""

import hashlib
import json
from pathlib import Path

from evidence_compiler.llm.base import LLMClient, T, Tier, Usage, generate_with_usage


class CachingLLM:
    def __init__(self, inner: LLMClient, directory: Path, *, namespace: str = ""):
        self.inner = inner
        self.name = f"cached:{inner.name}"
        self.model_for = getattr(inner, "model_for", lambda t: t)
        self.directory = directory
        self.namespace = namespace
        directory.mkdir(parents=True, exist_ok=True)

    def _key(self, task: str, system: str, prompt: str, schema: type, tier: Tier) -> str:
        model = getattr(self.inner, "model_for", lambda t: t)(tier)
        payload = json.dumps(
            [self.namespace, model, task, system, prompt, schema.model_json_schema()],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def generate(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> T:
        return self.generate_with_usage(
            task=task, system=system, prompt=prompt, schema=schema, tier=tier
        )[0]

    def generate_with_usage(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> tuple[T, Usage]:
        path = self.directory / f"{self._key(task, system, prompt, schema, tier)}.json"
        model = getattr(self.inner, "model_for", lambda t: t)(tier)
        if path.exists():
            return schema.model_validate_json(path.read_text()), Usage(model=model, cached=True)
        result, usage = generate_with_usage(
            self.inner, task=task, system=system, prompt=prompt, schema=schema, tier=tier
        )
        path.write_text(result.model_dump_json())
        return result, usage or Usage(model=model)
