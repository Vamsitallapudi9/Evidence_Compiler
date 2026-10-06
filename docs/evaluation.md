# Evaluation methodology

> **Status:** the harness is built and runs in CI with a scripted model
> (`make eval-fake`). **No real results have been published yet.** When they are, they
> will be committed alongside the exact model IDs and the generated report from
> `eval/results/`.

**Research question:** does explicit claim-level evidence compilation reduce unsupported
claims and improve evidence attribution compared with conventional RAG?

## Dataset

`data/demo/generate.py` builds a fictional company corpus with **fixed, designed
numbers**, so the ground truth is known by construction (`ground_truth.json`):

* `q1_fy2026_report.pdf`, `q2_fy2026_report.pdf` with prose and tables. The Q2 report
  mentions a healthcare product launch (a causal trap) and contains a planted
  prompt injection.
* `regional_sales.csv`: quarter × region × product line.
* `customer_segments.xlsx`: Segments and Industries sheets.
* Postgres `crm`: `customers`, `contract_events`. Churn is concentrated in European enterprise accounts.

`eval/questions.yaml` has 22 questions across lookup, derived, multi-source, SQL,
unanswerable, trap and injection categories. Each lists gold facts (numbers and/or
keywords), the sources a correct citation may point to, and traps.

## Systems

* **A: RAG.** BM25 top-12 over the same corpus (PDF passages, and every table and CRM row
  as a text chunk), then one model call.
* **B: RAG + citations.** Same as A, but the model returns sentences with chunk
  citations.
* **C: Evidence Compiler.** The full pipeline.

All three use the same model and the same tokenizer. The cache in `eval/.cache` makes
reruns reproducible.

## Metrics

| Metric | How |
|---|---|
| Answer accuracy (fact recall) | Deterministic. Gold numbers must appear in the answer (rounding-aware, unit-scaled) and keywords must match. |
| Calculation correctness | Fact recall restricted to `derived` facts. |
| Unsupported claim rate | Judge decomposes each answer into atomic claims, then labels each supported, unsupported or contradicted against a reference of all source data plus the ground truth. Rate = (unsupported + contradicted) / claims. |
| Citation correctness | Judge: do the cited passages support the sentence? (B, C) |
| Attribution accuracy | Deterministic. For covered facts, does a citing sentence point to an allowed source? |
| Abstention accuracy | Unanswerable questions: did the system say the evidence is insufficient? |
| Provenance completeness | C only. The share of supported claims whose chain passes `GraphValidator`. |

## Limitations

* The judge is an LLM and may share biases with the systems under test. It uses separate
  prompts and a full-data reference, but you should manually spot-check about 20% of
  the judged claims.
* Keyword and number matching can miss valid paraphrases. Per-question scores are in
  the report for inspection.
* The corpus is small and synthetic. It is designed to make specific failure modes
  measurable, not to estimate real-world accuracy.
* Phase 1 runs no ablations. `PipelineOptions` provides the switches for V2.

## Cost

A full run makes roughly 22 × (1 call for A + 1 for B + about 10–30 for C), plus judge
calls (about 2 + the number of citations per answer). Responses are cached in
`eval/.cache`, so reruns with unchanged prompts are free. Start with a subset
(`--questions q01,q10`) to check cost on your provider.

## Running

```bash
make eval                               # all systems, all questions
PYTHONPATH=backend/src backend/.venv/bin/python -m eval.run --systems C --questions q10,q14
make eval-fake                          # offline harness smoke test (meaningless numbers)
```

Results are written to `eval/results/<timestamp>.json` and `.md`. Do not hand-edit them.
