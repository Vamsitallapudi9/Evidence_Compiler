# HTTP API

Base URL `http://127.0.0.1:8000`. All routes are under `/api`, and JSON is used
unless noted. Interactive OpenAPI docs are at `/docs` while the API is running. Errors
use `{"detail": "..."}`. Request validation errors use FastAPI's 422 list format.

> The API has **no authentication** and is meant for a single local user. Don't expose
> it on a network; see [security.md](security.md).

## Health

`GET /api/health` → `{status, llm_configured, llm_provider, llm_model, pricing_configured}`

## Sources

| Method & path | Body | Returns |
|---|---|---|
| `GET /api/sources` | — | `SourceOut[]` |
| `POST /api/sources` | multipart `file` (`.pdf .csv .xlsx .docx .txt .md`) | `201 SourceOut`. Errors: 400 type, 413 size, 422 unreadable |
| `POST /api/sources/url` | `{url, name?}` | `201 SourceOut`. Errors: 400 blocked/invalid, 403 sign-in, 404, 413, 415 type, 422, 502/504 fetch |
| `POST /api/sources/huggingface` | `{dataset, config?, split?, max_rows?}` | `201 SourceOut`. Errors: 400 name, 403 gated, 404, 422, 502 |
| `POST /api/sources/postgres` | `{name, dsn, schema?}` | `201 SourceOut`. Errors: 422 cannot connect or no tables. The DSN is stored server-side and never returned |
| `DELETE /api/sources/{id}` | — | `204`, or 404 |
| `GET /api/sources/{id}/pages/{n}` | — | `{page, text, page_count}`: the canonical text that character offsets index into |

`SourceOut`: `{id, kind, name, ingested_at, evidence_count, tables, flagged_count, page_count?, url?, license?, fetched_at?}`
`kind` ∈ `pdf csv xlsx postgres web docx text huggingface`.

## Runs

| Method & path | Body | Returns |
|---|---|---|
| `POST /api/runs` | `{question}` (3–2000 chars) | `201 {run_id}` |
| `GET /api/runs` | — | `RunSummary[]`, newest first: `{id, question, status, created_at, error}` |
| `GET /api/runs/{id}` | — | `RunOut`: summary + `events`, `answer`, `usage`, `alive` |
| `POST /api/runs/{id}/cancel` | — | `202 {status: "cancelling"}`, 404, or 409 if not in progress |
| `GET /api/runs/{id}/events` | — | Server-sent events (below) |

`status` ∈ `pending running done failed cancelled`. A run that was in progress when the
server restarted comes back as `failed`, with an `error` starting `Interrupted:`.

### Live events (`text/event-stream`)

| Event | Data | When |
|---|---|---|
| `progress` | `{stage, message, data, ts}` | Pipeline steps: `fetch plan retrieve sql claims verify compile done cancel error` |
| `llm` | `LlmCall` | When each model call starts, and again when it ends (same `id`) |
| `heartbeat` | `{run_id, status, alive, elapsed_s, last_activity_s, current, usage}` | About every 2 seconds |
| `done` | `{status}` | Once, then the stream closes |

`LlmCall`: `{id, task, label, model, status: running|ok|error|cached, started_at, seconds, input_tokens, output_tokens, reasoning_tokens, cached_input_tokens, error}`.
`usage`: `{provider, model, calls, in_flight, failed_calls, cache_hits, input_tokens, output_tokens, reasoning_tokens, cached_input_tokens, est_cost_usd, calls_log?}`.
Token counts are those reported by the provider. `est_cost_usd` is only set when
pricing is configured.

### The answer

`Answer`: `{run_id, question, text, insufficient, claims[], gaps[], evidence{}, calculations{}, sources{}, graph, warnings[]}`

- **Markers:** `text` contains `[c:<claim_id>]` markers after each sentence's content.
  Every marker refers to an entry in `claims`.
- **Claims:** `Claim` is `{id, text, type, status, links[], calculation_id, checks[], entailment, entailment_note, reason, origin}`.
  - `type` ∈ `primary derived interpretation unsupported`
  - `status` ∈ `supported partial unsupported rejected`
  - `origin` ∈ `answer hypothesis`
- **Evidence:** `EvidenceItem` is `{id, source_ids, origin: primary|derived, creator: connector|sql|calc, text, fields, location, derived_from, calculation_id, security_flags}`.
- **Locations:** `location.kind` ∈ `pdf text table query calc`.
- **Model-written text:** `entailment_note` is written by the model. It's an
  explanation shown to you, never evidence.

## Evidence

`GET /api/evidence/{id}` → `EvidenceItem`. This also covers evidence created during a
run (SQL rows, calculations).
