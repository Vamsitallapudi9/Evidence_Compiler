import os

from evidence_compiler.config import Settings
from evidence_compiler.llm.base import LLMClient, LLMError, LLMRefusal, Tier
from evidence_compiler.llm.cache import CachingLLM


def llm_configured(settings: Settings | None = None) -> bool:
    provider = (settings or Settings()).llm_provider
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def make_llm(settings: Settings) -> LLMClient:
    """Build the configured LLM client. Add providers here (one adapter file each)."""
    if settings.llm_provider == "anthropic":
        from evidence_compiler.llm.anthropic_client import AnthropicClient

        client: LLMClient = AnthropicClient(settings)
    elif settings.llm_provider == "openai":
        from evidence_compiler.llm.openai_client import OpenAIClient

        client = OpenAIClient(settings)
    else:
        raise LLMError(f"unknown LLM provider '{settings.llm_provider}'")
    if settings.llm_cache:
        client = CachingLLM(client, settings.llm_cache_dir)
    return client


__all__ = ["LLMClient", "LLMError", "LLMRefusal", "Tier", "llm_configured", "make_llm"]
