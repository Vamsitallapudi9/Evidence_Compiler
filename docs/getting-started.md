# Getting started

## Requirements

| | Version | Notes |
|---|---|---|
| Python | 3.12+ | CI runs 3.12 and 3.14 |
| Node.js | 20.19+ | Needed for the Vite 8 frontend |
| An LLM API key | OpenAI (default) or Anthropic | The only external service the app needs |
| PostgreSQL | 17 (optional) | Only to use a database as a source |

macOS, Linux and WSL work. Commands below assume a Unix shell with `make`.

## 1. Install

```bash
git clone https://github.com/Vamsitallapudi9/Evidence_Compiler.git
cd Evidence_Compiler
cp .env.example .env
make setup
```

`make setup` creates `backend/.venv`, installs the backend in editable mode with dev
tools, and runs `npm install` in `frontend/`.

## 2. Configure the model

Edit `.env`:

```bash
EC_LLM_PROVIDER=openai          # or: anthropic
OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY=...
```

Defaults are `gpt-6-luna` for OpenAI, and `claude-opus-5-5` (strong) with
`claude-haiku-4-5` (fast) for Anthropic. Override them with `EC_STRONG_MODEL` and
`EC_FAST_MODEL`. Every setting is listed in [configuration.md](configuration.md).

Verify:

```bash
make check-llm
# provider: openai
#   ok: gpt-6-luna is available
#   ok: structured output works (supports)
```

If the model isn't found, the command prints similar model IDs your key can use.

## 3. Run

```bash
make demo-data    # generates the fictional demo corpus in data/demo/generated/
make dev          # API on http://127.0.0.1:8000, UI on http://localhost:5173
```

In a second terminal, you can load the demo corpus through the API:

```bash
make load-demo
```

Or add sources in the UI sidebar: upload a file, paste a link, or name a Hugging Face
dataset. Then ask a question. For the demo, try *"Why did Q2 revenue decline?"*.

## 4. Optional: PostgreSQL source

```bash
brew install postgresql@17 && brew services start postgresql@17   # macOS
make db-seed
```

`make db-seed` creates the `ec_demo` database and a **read-only** role `ec_reader`, and
prints the DSN to register. `make load-demo` registers it automatically. The demo role
password is a public, local-only value; set `EC_DEMO_PG_PASSWORD` before seeding (and
`EC_PG_DSN` to match) if your Postgres can be reached by anyone else. Docker users can
use `docker-compose.yml`; see the comment inside it.

## 5. Tests and benchmark

```bash
make test        # backend (pytest) + frontend (vitest); no API key or network needed
make lint
make eval-fake   # offline smoke test of the benchmark harness
make eval        # the real benchmark: uses your API key and costs money; see evaluation.md
```

Backend tests that need Postgres are skipped when the demo database isn't running.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Run shows **"Interrupted"** | The API restarted mid-run (`make dev` reloads on code changes). Click **Run again**. |
| Run monitor says **"Slow"** | No activity for 60s. A single model call can take a minute or two; the per-call timeout is `EC_LLM_TIMEOUT_S` (180s). |
| Run monitor says **"Looks stuck"** or **"Not running"** | Cancel, then **Run again**. Check the API terminal for errors. |
| `make check-llm` says the model was not found | Your key can't access that model ID. Pick one from the printed list and set `EC_STRONG_MODEL` / `EC_FAST_MODEL`. |
| "rate limited or out of credit" | Add credit to your provider account, or wait and retry. |
| "Cannot reach the backend" in the UI | Start the API (`make api`), or check that port 8000 is free. |
| Link fetch fails with "requires sign-in" | The link is not public. Download the file and upload it instead. |
| Web page gives "no readable text" | The page needs JavaScript to render. Use a PDF or print-to-PDF version. |
| Hugging Face 403 | The dataset is gated: accept its terms on huggingface.co and set `HF_TOKEN`. |
| Scanned PDF gives "no extractable text" | OCR isn't supported yet. |

## Resetting local data

All application state lives in `backend/var/` (SQLite, DuckDB, uploads), which is
gitignored. Stop the API and delete that folder to start fresh.
