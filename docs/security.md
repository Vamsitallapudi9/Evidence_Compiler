# Security model

**Scope:** Evidence Compiler is a **single-user tool that runs on your own machine**. The
threat model assumes the person operating it is trusted, and that the **content** it
reads (documents, web pages, datasets, database rows) and the **model's output** are
not. Report vulnerabilities as described in [SECURITY.md](../SECURITY.md).

The default failure mode is conservative: when evidence is missing or a check fails, the
answer says so ("Insufficient evidence available.") instead of hedging.

## Assets

- **Your API keys and database credentials.** Stored in `.env` or server-side only; never
  sent to the browser.
- **The data you add.** Stored locally under `backend/var/`.
- **The integrity of answers.** An answer must not present unsupported content as
  evidence-backed.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| **Prompt injection** in documents, pages or datasets | Source text is wrapped in `<evidence>` elements whose delimiters the text can't forge (`<` and `>` are escaped), and every prompt states that evidence is data. A heuristic scanner flags injection patterns per evidence item; flags are shown in the UI. The model has **no tools with side effects**, and its output is limited to a schema of IDs, quotes and operation names. The demo corpus includes a planted injection. |
| **Fabricated citations** | A cited ID that the run never showed the model makes the claim **rejected**. Quotes must occur verbatim. |
| **Wrong arithmetic** | The model never does arithmetic that reaches the answer. It names an operation; `calc/` computes it in `Decimal` from values read out of the cited evidence. Numbers in a claim must match evidence or calculation results. |
| **Circular provenance** | `Creator` has no LLM value, and a test forbids constructing evidence in `llm/`, `pipeline/` or `api/`. `GraphValidator` requires every chain to end at a registered source, with no cycles. |
| **Malicious generated SQL** | Parsed with `sqlglot` and accepted only if it is: a single statement; `SELECT` or set operations only; free of DDL, DML, `INTO`, `COPY`, `PRAGMA`, `ATTACH` and file, system or sleep functions; limited to allow-listed tables; and free of table functions. A row `LIMIT` is always added. |
| **Bypassing SQL validation** | Defence in depth. DuckDB queries use a fresh `read_only` connection with external access disabled. Postgres queries run in a read-only transaction with `statement_timeout`; the demo role has only `SELECT` grants and `default_transaction_read_only`. |
| **SSRF via links** | Only `http(s)` links, with no embedded credentials. The host is resolved, and private, loopback, link-local, multicast and reserved addresses are refused, re-checked on **every redirect hop**. Size limit and timeouts apply. `EC_ALLOW_PRIVATE_URLS` is off by default. |
| **Untrusted web content** | Pages are parsed as text with the standard-library HTML parser. Scripts are never executed. Content is treated exactly like an uploaded document. |
| **Malicious uploads** | Extension allow-list, a size limit enforced **while streaming** (never buffered past the limit), sanitized filenames, and parse errors returned as 422. `.xlsx` and `.docx` are checked for **zip bombs** (300 MB decompressed, ratio ≤ 200) before parsing. |
| **Credential leakage** | DSNs are stored in a separate database column and never serialized to API responses; source URIs are redacted. `.env`, `backend/var/` and caches are gitignored. Tests ignore `.env`. |
| **XSS** | React escapes all text. No raw-HTML rendering. External links render only for `http(s)` URLs, with `rel="noopener noreferrer"`. |
| **Hung or slow model calls** | Each call has a timeout (`EC_LLM_TIMEOUT_S`) and bounded retries. Runs can be cancelled, and interrupted runs are marked as such instead of hanging. |
| **Supply chain** | `package-lock.json` pins frontend dependencies. CI runs `pip-audit` and `npm audit`, and Dependabot proposes updates weekly. |

## Not in scope (by design, for now)

- **No authentication, rate limiting or multi-user isolation.** The API binds to
  `127.0.0.1`, and CORS allows only the local UI. **Don't expose it on a network or the
  internet.** Anyone who can reach the API can read your sources and spend your model
  credit.
- **The operator is trusted.** For example, a DSN you register is connected to as given,
  and `EC_ALLOW_PRIVATE_URLS=true` deliberately lifts the SSRF guard.
- **DNS rebinding** between the address check and the connection isn't prevented.
- **Heuristic injection flags** can be evaded. The structural defences above are what
  bound the impact.
- **Data residency:** evidence text and questions are sent to your configured LLM
  provider, under that provider's terms.

## Demo credentials

`make db-seed` creates a local, read-only demo role (`ec_reader`) whose default password
is public on purpose. It protects nothing secret, and the role can only read the
synthetic demo tables. If your Postgres is reachable by anyone else, set
`EC_DEMO_PG_PASSWORD` before seeding and `EC_PG_DSN` to match.
