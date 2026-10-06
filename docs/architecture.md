# Architecture

## Domain model (`core/models.py`)

| Object | Meaning |
|---|---|
| `Source` | A registered file or database. Content-hashed. |
| `EvidenceItem` | A unit of evidence: text, structured `fields`, a typed `Location`, `origin` (PRIMARY/DERIVED) and `creator` (CONNECTOR/SQL/CALC). |
| `Location` | `PdfLocation` (page + char span in canonical page text), `QueryLocation` (exact SQL, tables, row, timestamp), `CalcLocation`, `TableLocation`. |
| `Calculation` | A deterministic operation, its resolved inputs (each pointing at evidence), result and formula. Produces one DERIVED evidence item. |
| `Claim` | Atomic statement with `type`, `status`, `links` to evidence (`supports`, `derived_from`, `calculated_from`, `inferred_from`, `depends_on`; `contradicts`/`supersedes` reserved for V2), check results and the verifier verdict. |
| `Answer` | Prose with `[c:<id>]` markers, claims, gaps, the referenced evidence/calculations/sources, the evidence graph and warnings. |

IDs are content-addressed (`sha256` over source, location and content), so re-ingesting
the same file yields the same evidence IDs.

## The invariant

> AI-generated content cannot become evidence for another AI-generated claim.

This is enforced structurally, not by prompting:

1. `Creator` has no LLM member. PRIMARY evidence is minted only by connectors (or by a
   plain SQL row lookup); DERIVED evidence only by the calculation engine or a SQL
   aggregate. A test asserts that no module under `llm/`, `pipeline/` or `api/` constructs
   `EvidenceItem`.
2. Model output schemas (`pipeline/schemas.py`) contain only evidence **IDs**, verbatim
   **quotes**, and **requests** for named operations. No field can carry a number or a
   passage as fact.
3. `GraphValidator` walks each claim's provenance and requires it to end at registered
   sources, with no cycles and with type-appropriate links (a derived claim must
   link to derived evidence, an interpretation needs `inferred_from` links).
4. A cited ID that the run never showed the model makes the claim **REJECTED**.

## Pipeline (`pipeline/orchestrator.py`)

| Step | Who | Notes |
|---|---|---|
| Plan | LLM (fast tier) | Sub-questions, BM25 queries, **hypotheses to test** (tempting explanations are tested, not assumed) |
| Retrieve | BM25 | Reciprocal-rank fusion over question + sub-questions + queries |
| Structured | LLM writes SQL → `sql/validator.py` → `sql/executor.py` | One repair attempt on rejection; rows become evidence. When a result is cut off, the drafting step is told, so it doesn't reason from missing rows |
| Draft claims | LLM (strong) | Evidence wrapped as untrusted `<evidence>` data |
| Deterministic checks | code | `type_from_evidence` (the claim type is set from the cited evidence, not the model's label), `citations_exist`, `has_citations`, `quotes_verbatim`, `calculation`, `numbers_backed`, `provenance` |
| Entailment | LLM, isolated | Sees only the claim, its cited evidence and the calc trace |
| Classify | code | Integrity failure → REJECTED; other failure → UNSUPPORTED; entailment partial → PARTIAL |
| Compile | LLM + code post-check | Claims are given short markers (`[c:1]`), which code maps back to claim IDs. Sentences without a valid marker, or with numbers absent from their claims, are removed and reported |

`PipelineOptions` exposes switches (`use_sql`, `verify_entailment`, `enforce_checks`,
`test_hypotheses`) for the planned ablation studies.

## Extension points

* **Connectors**: implement `ingest(path, name) -> IngestResult` and register a suffix in
  `ingestion/registry.py`.
* **Retrievers**: implement the `Retriever` protocol (`index`, `remove_source`, `search`).
* **LLM providers**: implement `LLMClient.generate(task, system, prompt, schema, tier)` and
  add it to `llm.make_llm`.
* **Calculations**: add an `OpSpec` to `calc/operations.py`.
* **Store**: the API depends only on `store/repositories.Repository`.

## Links and Hugging Face datasets

* **Links** (`ingestion/fetch.py`, `ingestion/url.py`). The server fetches the link and
  routes it by content type: PDF goes to the PDF connector, HTML to the web connector,
  `.docx` to Word, CSV/XLSX to the tabular connector, text/markdown to the text connector.
  Share links are rewritten to direct downloads (Google Docs → docx export, Sheets → CSV,
  Drive → download, GitHub blob → raw, arXiv abs → PDF). The snapshot is kept, and its
  content hash is the source ID, so evidence stays stable even if the page later changes.
  `metadata.url` and `metadata.fetched_at` record where the snapshot came from and when.
  When a question contains links, the run fetches them first (`stage: "fetch"` events)
  and answers **only** from those sources.
* **Hugging Face** (`ingestion/huggingface.py`). Rows come from the public datasets-server
  API. Large splits are sampled with evenly spaced pages, because many datasets are
  sorted (taking the first N IMDB rows gives only negative reviews). `row_idx` keeps the
  original dataset row number. Class labels gain a `<col>_name` column. Rows load into
  DuckDB for SQL, and long text columns also become PRIMARY passage evidence (one per
  row) that is searchable and quotable. The licence is recorded from the dataset card.

## Run monitoring (`llm/meter.py`, `app.py`)

Each run gets a `MeteredLLM` wrapped around the configured client:

- **Call log:** every model call is recorded twice, when it starts and when it ends,
  with its task, a human-readable label ("Verifying claim 3 of 20"), model, token
  counts and duration.
- **Live streaming:** the run manager streams these records as `llm` events, plus a
  `heartbeat` every ~2s (alive, seconds since the last activity, current step, usage
  totals).
- **Persistence:** usage is saved after every call, so totals survive a crash.
- **Cancellation:** checked before every call and at every step boundary.
- **Startup recovery:** on startup, runs left `pending` or `running` by a previous
  process are marked `failed` with an `Interrupted:` error, instead of hanging forever.

## LLM providers (`llm/`)

`LLMClient.generate(task, system, prompt, schema, tier)` returns a validated Pydantic
object. Adapters may also implement `generate_with_usage` to report tokens.

| Provider | Adapter | Structured output | Defaults |
|---|---|---|---|
| OpenAI (default) | `openai_client.py` | Responses API, `responses.parse(text_format=…)`, strict JSON schema | `gpt-6-luna` for both tiers |
| Anthropic | `anthropic_client.py` | `messages.parse(output_format=…)` (forced tool use is rejected by current models) | `claude-opus-5-5` / `claude-haiku-4-5` |

`FakeLLM` drives the tests. `CachingLLM` makes benchmark reruns reproducible.
