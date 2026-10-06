# Contributing

Thanks for your interest! Bug reports, docs fixes, benchmark questions and connectors are
all welcome.

## Setup

```bash
cp .env.example .env    # an API key is only needed to run the app, not the tests
make setup
make demo-data
make test && make lint
```

Optional: `make db-seed` (local Postgres) enables the Postgres tests. They're skipped
otherwise.

## Ground rules for changes

1. **Keep the invariant.** Model output must never become evidence. Only connectors
   (`ingestion/`), the SQL executor (`sql/`) and the calculator (`calc/`) may construct
   `EvidenceItem`. A test enforces this.
2. **Deterministic first.** If code can check something reliably, code checks it. Don't
   move a check into a prompt.
3. **No fabricated results.** Benchmark numbers in docs must come from a committed
   results file produced by `make eval`.
4. **Tests must be hermetic.** No network, API keys or `.env`. Use `FakeLLM` and mocked
   HTTP transports (see `backend/tests/`).
5. **Security-sensitive areas** need tests that prove the defence: SQL validation, link
   fetching, upload parsing, provenance.

## Style

- **Python:** `ruff` (lint and format), type hints, small modules. **TypeScript:** strict
  mode, `oxlint`.
- **Comments:** explain *why*, not what.
- **Commits:** imperative, scoped messages (`fix(sql): reject table functions`).

## Pull requests

Describe the change, why it's needed, and how you tested it. CI must pass: lint, tests on
Python 3.12 and 3.14, the frontend build and tests, and dependency audits. For larger
changes, open an issue first, and consider adding an ADR in `docs/adr/`.
