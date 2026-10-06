# Changelog

All notable changes are listed here. This project follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [0.1.0] - 2026-10-06

First public release (Phase 1 MVP).

### Added
- **Evidence model:** typed, content-addressed evidence, claims, calculations and an
  evidence graph. The invariant that model output can never become evidence is
  enforced in code.
- **Connectors:** PDF, Word, text/Markdown, CSV, Excel, PostgreSQL, links (web pages,
  Google Docs/Sheets/Drive, GitHub, arXiv) and Hugging Face datasets.
- **Retrieval and SQL:** BM25 retrieval, plus model-written SQL that is validated with
  sqlglot and executed read-only.
- **Checks:** a deterministic calculation engine, and code checks on citations, quotes,
  numbers, provenance and claim types, followed by an isolated model check of each
  claim.
- **Answers:** testing of tempting explanations, and answer compilation with
  per-sentence claim markers and a code post-check.
- **LLM providers:** OpenAI (default) and Anthropic adapters behind one interface, with
  timeouts, a response cache, and a fake client for tests.
- **UI:** answers with typed claims, a claim inspector, the evidence graph, and a live
  run monitor (tokens, current step, stuck detection, cancel, run again).
- **Benchmark:** a harness with 22 questions comparing RAG, RAG + citations and Evidence
  Compiler. No results are published yet.
- **Security hardening:** SSRF guards, zip-bomb checks, bounded uploads, read-only SQL
  connections, and injection flagging.
- **Repository:** CI on Python 3.12 and 3.14 plus the frontend, dependency audits,
  Dependabot, and documentation.
