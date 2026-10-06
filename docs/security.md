# Security model

The default failure mode is conservative: when evidence is missing or a check fails,
the answer says so ("Insufficient evidence available.") instead of hedging.

| Threat | Mitigation |
|---|---|
| Prompt injection inside documents | Source text is wrapped in `<evidence>` elements whose delimiters it cannot forge (`<`/`>` escaped). System prompts say evidence is data. Heuristic scanner flags injection patterns per evidence item (`security_flags`), shown in the UI. The model has no tools with side effects, and its output is schema-constrained. The demo corpus contains a planted injection. |
| Hallucinated citations | Cited IDs must be in the run's evidence pool, otherwise the claim is REJECTED. Quotes must occur verbatim. |
| Incorrect calculations | The model never does arithmetic that reaches the answer. It names an operation; `calc/` computes it in `Decimal` from values read out of evidence. Numbers in claim text must match evidence or calculation results. |
| Generated SQL / SQL injection | `sqlglot` parse: one statement, `SELECT`/set operations only, no DDL/DML/`INTO`/`COPY`/`PRAGMA`/`ATTACH`, a denylist of file/system/sleep functions, table allowlist from schema cards, no table functions, a forced `LIMIT`. |
| Validator bypass | Defence in depth. DuckDB queries use a fresh `read_only` connection with `enable_external_access=false`. Postgres queries run as `ec_reader` (SELECT-only grants, `default_transaction_read_only`), in a read-only transaction with `statement_timeout`. |
| Provenance corruption | Content-addressed IDs. `GraphValidator` checks every chain terminates in a registered source. |
| Credential leakage | DSNs are stored in a separate column, never serialized to the API; source URIs are redacted. |
| Server-side request forgery via links | Only http(s). Hosts are resolved and private, loopback, link-local, multicast and reserved addresses are refused, re-checked on **every redirect hop**. No embedded credentials. Size cap and timeouts. Residual risk: DNS rebinding between check and connect. Acceptable for a single-user local tool; pin resolved IPs before multi-user deployment. |
| Untrusted web content | Fetched pages are treated exactly like uploaded documents: snapshotted, scanned for injection, wrapped as untrusted evidence. Scripts are never executed; text is extracted with a plain HTML parser. |
| Malicious uploads | Suffix allowlist (pdf/csv/xlsx), size limit, sanitized filenames, parsing errors returned as 422. |
| Data leakage to the model provider | Only retrieved evidence and schema cards (with three sample rows) are sent to the Claude API. Everything else stays local. |

Known gaps for later phases: no authentication (single local user), heuristic
injection detection only, no OCR for scanned PDFs, and no stale-data or
source-authority checks yet.
