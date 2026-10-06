# Limitations

This is a Phase 1 MVP. This page lists what it does **not** do, and where its
guarantees stop, so nobody has to discover them the hard way.

## What the checks do and don't guarantee

- **Code-checked:** citations point at real evidence. Quotes occur verbatim. Each number
  in a claim matches its evidence or calculation (allowing for rounding). Calculations
  recompute. Every provenance chain ends at a registered source. Model output can't
  become evidence.
- **Model-checked, so it can be wrong:** whether the cited evidence actually *supports*
  the claim's meaning (entailment), and whether an AI interpretation is reasonable. A
  claim can pass every code check and still be judged wrong by a human. The verifier
  sees only the claim and its cited evidence, but it is still a language model.
- **Gaps in retrieval aren't detected.** If the retrieval step misses relevant evidence,
  the system can't know. It answers from what it found, and may mark something
  "unsupported" that a source elsewhere does support. BM25 is keyword-based and misses
  paraphrases.
- **No contradiction detection yet.** If two sources disagree, both claims can pass.
  The `contradicts` relation exists in the data model for Phase 2.
- **Number matching is pattern-based.** It reads numbers like `$7.4M`, `8.4%` and
  `1,200`, and ignores years and labels such as `Q2`. Unusual formats (spelled-out
  numbers, ranges, non-English separators) may not match.
- **Calculations** are limited to difference, percent change, ratio, share of total, sum
  and mean, applied to numbers taken from cited evidence.

## Security posture

- **No authentication or multi-user isolation.** The API binds to `127.0.0.1` and
  allows CORS only from the local dev UI. Don't expose it on a network.
- **Prompt-injection detection is heuristic.** Source text is fenced as untrusted data
  and flagged with pattern rules. Determined injections can evade the flags; the
  structural defences (schema-limited output, no model-created evidence, read-only SQL)
  are what limit the damage.
- **DNS rebinding** between the link-safety check and the actual connection isn't
  prevented. That's acceptable for a local single-user tool, not for a hosted service.
- **What reaches your LLM provider:** your evidence and questions are sent to it. Don't
  add sources you aren't allowed to share with that provider.

## Sources

- No OCR, so scanned PDFs have no text. Complex PDF layouts (multi-column, rotated
  tables) can split or merge paragraphs.
- Web pages that render with JavaScript, or sit behind a sign-in, can't be read.
- Hugging Face datasets are **sampled** (2,000 rows by default, evenly spread). Answers
  cover the sample, not the full dataset, and the source records which rows were loaded.
- Very large corpora work but are slow: retrieval is in-memory BM25, and each claim is
  verified with its own model call.

## Evaluation

- **No benchmark results are published yet.** The benchmark (22 questions, systems
  A/B/C) is built and smoke-tested with a scripted model. Real numbers will come only
  from real runs (`make eval`).
- **The benchmark corpus is small and synthetic.** It's designed to expose specific
  failure modes, not to estimate real-world accuracy. Some metrics use an LLM judge,
  with the biases that brings (see [evaluation.md](evaluation.md)).

## Cost and speed

A typical question makes about 6–30 model calls: planning, SQL, drafting, one
verification per claim, and compilation. That takes roughly 30 seconds to 3 minutes.
The run monitor shows live token counts. Batched verification is on the
[roadmap](roadmap.md).
