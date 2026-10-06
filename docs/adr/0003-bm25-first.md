# ADR 0003: BM25 retrieval first

**Status:** accepted

**Decision.** Use `rank_bm25` behind a `Retriever` protocol. It is deterministic, local,
dependency-light and adequate for small corpora with domain terms and numbers.
Structured data is reached through SQL, not retrieval.

**Consequences.** Semantic recall is weaker on paraphrased questions. Embedding or
hybrid retrievers can be added later without touching the pipeline.
