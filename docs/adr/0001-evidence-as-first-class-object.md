# ADR 0001: Evidence is a first-class object

**Status:** accepted

**Context.** RAG systems pass retrieved text to a model as anonymous context, so the
link between a statement and its support is lost or is only a chunk-level citation.

**Decision.** Model evidence as typed, content-addressed `EvidenceItem`s with precise
locations, and model answers as atomic `Claim`s that reference evidence through typed
links. The answer text is compiled from claims and carries claim markers.

**Consequences.** Every statement can be inspected down to a page span, table row or
SQL query. There's more machinery than RAG, plus several extra model calls per question.
