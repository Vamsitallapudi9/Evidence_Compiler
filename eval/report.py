"""Markdown report generated from a results file. Every number comes from the run."""

from pathlib import Path

from eval.metrics import QuestionScore

ROWS = [
    ("fact_recall", "Answer accuracy (gold-fact recall)", "↑"),
    ("question_accuracy", "Questions fully correct", "↑"),
    ("derived_fact_recall", "Calculation correctness (derived facts)", "↑"),
    ("unsupported_claim_rate", "Unsupported claim rate", "↓"),
    ("contradicted_claims", "Contradicted claims (count)", "↓"),
    ("abstention_accuracy", "Abstains on unanswerable questions", "↑"),
    ("false_abstention_rate", "False abstention on answerable questions", "↓"),
    ("citation_coverage", "Sentences carrying citations", "↑"),
    ("citation_correctness", "Citation correctness", "↑"),
    ("attribution_accuracy", "Evidence attribution accuracy", "↑"),
    ("provenance_completeness", "Provenance completeness", "↑"),
    ("atomic_claims", "Atomic claims judged", ""),
    ("mean_seconds", "Mean seconds / question", ""),
    ("errors", "Errors", "↓"),
]


def _fmt(v: object) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.1%}" if v <= 1 else f"{v:.2f}"
    return str(v)


def write_report(
    results_path: Path,
    meta: dict,
    summary: dict,
    scores: list[QuestionScore],
    questions: list[dict],
) -> Path:
    systems = list(summary)
    label = {"A": "A: RAG", "B": "B: RAG + citations", "C": "C: Evidence Compiler"}
    lines = [
        f"# Evaluation results — {meta['timestamp']}",
        "",
        "> **FAKE RUN — plumbing smoke test with a scripted model; numbers are meaningless.**"
        if meta.get("fake")
        else f"Models: strong=`{meta['strong_model']}`, fast=`{meta['fast_model']}`. "
        f"Questions: {len(meta['questions'])}. Postgres source: {meta['postgres']}. "
        f"LLM calls (incl. judge, cache hits count): {meta['total_llm_calls']}.",
        "",
        "| Metric | " + " | ".join(label.get(s, s) for s in systems) + " |",
        "|---|" + "---|" * len(systems),
    ]
    for key, name, arrow in ROWS:
        if not any(key in summary[s] for s in systems):
            continue
        lines.append(
            f"| {name} {arrow} | " + " | ".join(_fmt(summary[s].get(key)) for s in systems) + " |"
        )
    lines += [
        "",
        "Fact recall, derived-fact recall, abstention and attribution are scored "
        "deterministically against `eval/questions.yaml`. Unsupported claim rate and citation "
        "correctness use an LLM judge (see `docs/evaluation.md` for its limitations).",
        "",
        "## Per question",
        "",
        "| Question | Category | " + " | ".join(systems) + " |",
        "|---|---|" + "---|" * len(systems),
    ]
    by = {(s.question_id, s.system): s for s in scores}
    for q in questions:
        cells = []
        for sys_name in systems:
            s = by.get((q["id"], sys_name))
            if s is None:
                cells.append("—")
            elif s.error:
                cells.append("error")
            elif not s.answerable:
                cells.append(
                    f"{'abstained' if s.abstained else 'answered'}; {s.unsupported}/{len(s.verdicts)} unsup."
                )
            else:
                cells.append(
                    f"{s.facts_covered}/{s.facts_total} facts; {s.unsupported}/{len(s.verdicts)} unsup."
                )
        lines.append(f"| {q['id']} {q['question']} | {q['category']} | " + " | ".join(cells) + " |")
    lines += ["", f"Raw results: `{results_path.name}`", ""]
    md = results_path.with_suffix(".md")
    md.write_text("\n".join(lines))
    return md
