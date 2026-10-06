# Evidence Compiler

AI systems are good at generating answers but weak at making the evidential basis of
those answers explicit. **Evidence Compiler** represents source evidence, claims,
derivations and interpretations as structured objects and compiles them into
*auditable answers*. You can click any important statement and see exactly which
passage, table row, SQL result or deterministic calculation it rests on, and what the
system could **not** establish.

> **Core rule.** Every important claim must either trace back to primary source
> evidence, be deterministically derived from primary evidence, or be explicitly
> labelled as an AI-supported interpretation. Otherwise it is unsupported.

This is not a claim to "solve hallucination". The aim is narrower and testable: make
the provenance of an answer inspectable, and measure whether claim-level evidence
compilation reduces unsupported statements compared with conventional RAG.

## How it differs from RAG

| | RAG / RAG + citations | Evidence Compiler |
|---|---|---|
| Retrieved material | context for the model | typed, content-addressed **evidence objects** |
| Unit of answer | paragraph | **atomic claims**, each linked to evidence |
| Numbers | whatever the model writes | read from evidence or computed by a **deterministic calculation engine** |
| Tables / databases | flattened into text | **validated read-only SQL**; each result row is evidence with its query |
| Citations | point at a chunk | verbatim quote spans, checked to exist; fabricated IDs are **rejected** |
| Unsupported statements | blend in | **explicitly listed**, including tested-and-failed hypotheses |
| The model as a source | implicit | **impossible by construction**: the model has no code path that creates evidence |

## Example

Ask *"Why did Q2 revenue decline?"* over the demo corpus (two quarterly-report PDFs, a
regional sales CSV, a customer-segment workbook and a CRM Postgres database). The output
has this shape (illustrative, taken from the scripted end-to-end test in
`backend/tests/fake_scenario.py`; live model output will be worded differently):

```
Q2 revenue declined 8.4% to $114.0 million.            PRIMARY  q2_fy2026_report.pdf p.1 (quote highlighted)
Europe accounted for approximately 71% of the decline. DERIVED  share_of_total: −7,400,000 / −10,400,000 × 100 = 71.15%
                                                                ← SQL over regional_sales.csv (query shown)
Enterprise was the largest negative segment (−$6.9M).  DERIVED  SQL aggregate over customer_segments.xlsx
Europe appears to be the primary driver.               AI INTERPRETATION, inferred from the rows above
"Healthcare customers caused the decline."             UNSUPPORTED (tested hypothesis; Healthcare revenue grew)
```

## Architecture

```
question → plan (sub-questions, search terms, hypotheses to test)
         → retrieve: BM25 over document evidence  +  LLM-written SQL → sqlglot validation → read-only execution
         → draft claims (cite evidence IDs, verbatim quotes, request calculations by name)
         → deterministic checks: IDs exist · quotes verbatim · calculation runs · numbers backed · provenance valid
         → isolated entailment check (model sees only the claim + its cited evidence)
         → classify (primary / derived / interpretation / unsupported / rejected)
         → compile prose from verified claims, post-check every sentence → answer + evidence graph
```

The LLM handles interpretation, claim drafting, semantic verification and prose.
Deterministic code handles calculations, SQL validation, IDs, quote matching, number
checks, provenance and metrics. See [docs/architecture.md](docs/architecture.md) and
the [ADRs](docs/adr/).

```
backend/src/evidence_compiler/
  core/        models, content-addressed IDs, number parsing, provenance invariants, graph
  ingestion/   PDF, CSV/Excel (→ DuckDB), Word/HTML/text, links (safe fetch), Hugging Face, Postgres
  retrieval/   Retriever protocol + BM25
  sql/         sqlglot validator, read-only executors (DuckDB, Postgres)
  calc/        closed set of Decimal operations
  llm/         LLMClient protocol, OpenAI + Claude adapters (structured outputs), cache, fake
  pipeline/    schemas, prompts, verification, compiler, orchestrator
  security/    untrusted-text delimiting, prompt-injection flags
  store/, api/ SQLite app state, FastAPI + SSE
frontend/      React + TypeScript UI: answer with typed claim spans, claim inspector, evidence graph
eval/          benchmark questions, baselines A/B, judge, metrics, report
data/demo/     deterministic demo corpus generator + Postgres seed
```

## Quickstart (macOS, everything local except the LLM API)

```bash
cp .env.example .env               # set EC_LLM_PROVIDER and OPENAI_API_KEY or ANTHROPIC_API_KEY
make setup                         # backend venv + frontend deps
make check-llm                     # confirm key + model ID work
brew install postgresql@17 && brew services start postgresql@17
make db-seed                       # demo corpus + ec_demo DB + read-only ec_reader role
make dev                           # API :8000, UI http://localhost:5173
make load-demo                     # (other terminal) ingest the demo corpus + Postgres
```

Then ask *"Why did Q2 revenue decline?"*. Postgres is optional: everything else works
without it.

```bash
make test        # backend (pytest) + frontend (vitest); no API key needed
make eval-fake   # smoke-test the benchmark harness offline
make eval        # real A/B/C benchmark (uses the configured LLM; responses cached in eval/.cache)
```

## Evaluation

`eval/` compares **A** (BM25 RAG), **B** (RAG + chunk citations) and **C** (Evidence
Compiler) on 22 questions with known ground truth: lookups, derived values,
multi-source "why" questions, SQL questions, unanswerable questions, a causal trap and
a prompt-injection probe. Metrics include answer accuracy, derived-fact accuracy,
**unsupported claim rate**, citation correctness, attribution accuracy, abstention and
provenance completeness. Methodology and limitations are in
[docs/evaluation.md](docs/evaluation.md). **No results are included until the benchmark
has been run**; `make eval` writes them to `eval/results/`.

## Status

Phase 1 (MVP) covers ingestion of PDF, CSV, Excel, Word, text, Postgres, **links** (PDFs,
web pages, Google Docs/Sheets/Drive, GitHub, arXiv — fetched and snapshotted server-side;
paste a link into a question to answer from it) and **Hugging Face datasets** (by name;
evenly sampled across the split, tables queried with SQL, long text columns indexed as
passages), claim-level provenance,
deterministic calculations, verification, unsupported-claim detection, a basic
evidence graph, the UI and the minimal benchmark. Planned for V2: contradiction
detection, source authority, temporal/version-aware evidence, embeddings, ablation
studies, observability and cost tracking, and a human verification workflow.
