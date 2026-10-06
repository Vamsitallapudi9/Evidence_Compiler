# Roadmap

Phase 1 (this release) proves the core loop: evidence objects, claim-level provenance,
deterministic checks, an auditable UI, and a benchmark harness. Phase 2 makes it cheaper,
faster and more trustworthy, and measures whether it actually helps.

## Phase 2: proposed

### 1. Dynamic model routing
Route each step to the cheapest model that is good enough, and escalate when signals
say it isn't.

- **Per-step defaults:** planning, SQL and most verifications on a small model; claim
  drafting and hard verifications on a strong model.
- **Escalation triggers:**
  - a schema-validation failure
  - an SQL repair loop
  - a verifier verdict of `partial`
  - disagreement between two cheap verifiers
  - a high claim count or a long evidence pool
  - claims involving causality or comparisons
- **Budget-aware routing:** a per-run token or dollar budget and latency target. The
  router trades off depth (how many claims get a strong verification) against cost.
- **Provider fallback:** on rate limits, timeouts or refusals, retry on another
  configured provider, with the same structured-output contract.
- **Learned router (later):** train a lightweight classifier on benchmark logs to
  predict when a cheap model's output will fail checks.
- **Auditability:** every routing decision (model, reason, cost) goes into the run's
  call log and the answer's provenance. Routing must never weaken the core invariant:
  model output still can't become evidence, whichever model wrote it.
- **Evaluation:** report the cost vs unsupported-claim-rate frontier for fixed models
  vs routing.

### 2. Speed and cost
- **Batched verification:** verify several claims per call, with per-claim isolation
  kept by structured output. This cuts calls by about 4×.
- **Streaming partial answers:** show verified claims as they pass, before the final prose.
- **Prompt caching** of the evidence block across drafting and verification.

### 3. Trust
- **Contradiction engine:** detect when sources disagree on the same metric, period and
  entity, explain likely causes (definitions, periods, versions), and surface it in the
  answer.
- **Source authority and freshness:** prefer the primary system of record, flag stale
  sources, and track document versions (`supersedes`).
- **Human review workflow:** reviewers accept or reject claims, and their decisions feed
  back into evaluation.
- **Second-opinion verification:** an independent model family verifies high-stakes claims.

### 4. Retrieval
- **Hybrid retrieval:** BM25 plus embeddings (local or API) behind the existing
  `Retriever` protocol.
- **Retrieval gap detection:** ask "what evidence would refute this?" and search for it.
- **Incremental indexing**, and persistence for large corpora.

### 5. Evaluation
- Publish **real A/B/C results**, and ablations (no SQL, no verification, no
  enforcement, no hypothesis testing; the switches already exist in `PipelineOptions`).
- **Public datasets:** add benchmarks built on FinQA / TAT-QA (numeric reasoning over
  reports), QASPER (scientific papers), FEVER (claim verification) and HotpotQA
  (multi-hop).
- **Manual audit:** have humans audit a sample of judge decisions, and report
  agreement.

### 6. Product
- **Audit report export:** a PDF or HTML with every claim, quote and calculation.
- **OCR** for scanned PDFs, and better table extraction.
- **More connectors:** REST/JSON APIs, Notion, Confluence, S3.
- **Deployment mode:** authentication, multi-user workspaces, Docker images, and
  OpenTelemetry traces.

Ideas and votes welcome: open an issue.
