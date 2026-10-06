"""Runtime configuration, read from the environment (and an optional .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
if not os.getenv("EC_SKIP_DOTENV"):  # tests set this so a developer's .env can't leak in
    load_dotenv(REPO_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


_DEFAULT_MODELS = {
    "anthropic": ("claude-opus-5-5", "claude-haiku-4-5"),
    "openai": ("gpt-6-luna", "gpt-6-luna"),
}


def _provider() -> str:
    return os.getenv("EC_LLM_PROVIDER", "openai").strip().lower()


def _model(env: str, index: int) -> str:
    return os.getenv(env) or _DEFAULT_MODELS.get(_provider(), _DEFAULT_MODELS["anthropic"])[index]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("EC_DATA_DIR", REPO_ROOT / "backend" / "var"))
    )
    llm_provider: str = field(default_factory=_provider)
    strong_model: str = field(default_factory=lambda: _model("EC_STRONG_MODEL", 0))
    fast_model: str = field(default_factory=lambda: _model("EC_FAST_MODEL", 1))
    openai_reasoning_effort: str | None = field(
        default_factory=lambda: os.getenv("EC_OPENAI_REASONING_EFFORT") or None
    )
    strong_effort: str = field(default_factory=lambda: os.getenv("EC_STRONG_EFFORT", "medium"))
    llm_fallbacks: bool = field(default_factory=lambda: _bool("EC_LLM_FALLBACKS", True))
    llm_cache: bool = field(default_factory=lambda: _bool("EC_LLM_CACHE", False))
    llm_timeout_s: float = field(
        default_factory=lambda: float(os.getenv("EC_LLM_TIMEOUT_S", "180"))
    )
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("EC_LLM_MAX_RETRIES", "2")))
    price_input_per_m: float | None = field(
        default_factory=lambda: float(v) if (v := os.getenv("EC_PRICE_INPUT_PER_M")) else None
    )
    price_output_per_m: float | None = field(
        default_factory=lambda: float(v) if (v := os.getenv("EC_PRICE_OUTPUT_PER_M")) else None
    )
    pg_dsn: str | None = field(default_factory=lambda: os.getenv("EC_PG_DSN"))
    retrieval_k: int = field(default_factory=lambda: int(os.getenv("EC_RETRIEVAL_K", "12")))
    sql_max_rows: int = field(default_factory=lambda: int(os.getenv("EC_SQL_MAX_ROWS", "200")))
    sql_timeout_ms: int = field(default_factory=lambda: int(os.getenv("EC_SQL_TIMEOUT_MS", "5000")))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("EC_MAX_UPLOAD_MB", "25")))
    hf_token: str | None = field(default_factory=lambda: os.getenv("HF_TOKEN") or None)
    hf_max_rows: int = field(default_factory=lambda: int(os.getenv("EC_HF_MAX_ROWS", "20000")))
    allow_private_urls: bool = field(default_factory=lambda: _bool("EC_ALLOW_PRIVATE_URLS", False))

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "evidence_compiler.sqlite"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "tabular.duckdb"

    @property
    def llm_cache_dir(self) -> Path:
        return self.data_dir / "llm_cache"


def get_settings() -> Settings:
    return Settings()
