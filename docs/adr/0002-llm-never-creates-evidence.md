# ADR 0002: The LLM never creates evidence

**Status:** accepted

**Context.** If model output can be stored as evidence, provenance can become circular:
model → "evidence" → model claim.

**Decision.** `Creator` has no LLM value. Connectors mint PRIMARY evidence, and the
calculation engine and SQL executor mint DERIVED evidence. Model output schemas carry
only IDs, verbatim quotes and named-operation requests. A test forbids `EvidenceItem(`
construction in `llm/`, `pipeline/` and `api/`.

**Consequences.** Interpretations are allowed but are always labelled and rest on cited
evidence. Arithmetic is restricted to a closed operation set, so new kinds of derivation
need code.
