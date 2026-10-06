# Configuration

Settings are read from environment variables, and from `.env` in the repo root if
present (see `.env.example`). Real environment variables take precedence over
`.env`. The source of truth is `backend/src/evidence_compiler/config.py`.

## Model

| Variable | Default | Description |
|---|---|---|
| `EC_LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | — | Required for `openai` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | — | Required for `anthropic` |
| `EC_STRONG_MODEL` | `gpt-6-luna` / `claude-opus-5-5` | Model for claim drafting, verification, SQL, compilation |
| `EC_FAST_MODEL` | `gpt-6-luna` / `claude-haiku-4-5` | Model for question planning |
| `EC_OPENAI_REASONING_EFFORT` | unset | `low`, `medium` or `high` for OpenAI reasoning models; unset means the model default |
| `EC_STRONG_EFFORT` | `medium` | Anthropic effort level for the strong tier |
| `EC_LLM_FALLBACKS` | `true` | Anthropic server-side refusal fallback on supported models |
| `EC_LLM_TIMEOUT_S` | `180` | Per-call timeout. A hung call fails instead of stalling the run |
| `EC_LLM_MAX_RETRIES` | `2` | SDK retries for transient errors |
| `EC_LLM_CACHE` | `false` | Cache model responses on disk (`backend/var/llm_cache`) |
| `EC_PRICE_INPUT_PER_M` / `EC_PRICE_OUTPUT_PER_M` | unset | Your price in USD per 1M tokens. When both are set, the UI shows an estimated cost |

## Retrieval and SQL

| Variable | Default | Description |
|---|---|---|
| `EC_RETRIEVAL_K` | `12` | BM25 passages per search query |
| `EC_SQL_MAX_ROWS` | `200` | Hard row limit added to every generated query |
| `EC_SQL_TIMEOUT_MS` | `5000` | Postgres `statement_timeout` for generated queries |

## Sources

| Variable | Default | Description |
|---|---|---|
| `EC_MAX_UPLOAD_MB` | `25` | Maximum upload and link-download size |
| `EC_ALLOW_PRIVATE_URLS` | `false` | Allow fetching links on private, loopback or LAN addresses. Keep `false` unless you need intranet links |
| `HF_TOKEN` | unset | Hugging Face token, only for gated or private datasets |
| `EC_HF_MAX_ROWS` | `20000` | Upper bound on rows loaded per Hugging Face dataset |
| `EC_PG_DSN` | demo DSN | DSN used by `make load-demo`, the benchmark and tests |
| `EC_DEMO_PG_PASSWORD` | `ec_reader_local_only` | Password `make db-seed` gives the demo read-only role |

## Storage

| Variable | Default | Description |
|---|---|---|
| `EC_DATA_DIR` | `backend/var` | SQLite app state, DuckDB tables, uploads, caches |

## Development

| Variable | Description |
|---|---|
| `EC_API_TARGET` | Backend URL the Vite dev server proxies `/api` to (default `http://localhost:8000`) |
| `EC_SKIP_DOTENV` | Set by the test suite so a developer's `.env` can't affect tests |
| `EC_TEST_PG_DSN` | Postgres DSN the test suite uses for Postgres tests |
