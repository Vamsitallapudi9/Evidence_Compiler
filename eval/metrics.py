"""Deterministic scoring of answers against gold facts, plus aggregation."""

from dataclasses import dataclass, field
from decimal import Decimal

from evidence_compiler.core.numbers import approx_equal, parse_numbers
from evidence_compiler.pipeline.compiler import split_sentences

from eval.systems import SystemOutput


def fact_covered(fact: dict, text: str) -> bool:
    low = text.lower()
    nums = parse_numbers(text, skip_years=False)
    for gold in fact.get("numbers", []):
        g = Decimal(str(gold))
        if not any(approx_equal(n, g) for n in nums):
            return False
    if any(k.lower() not in low for k in fact.get("keywords_all", [])):
        return False
    anys = fact.get("keywords_any", [])
    return not (anys and not any(k.lower() in low for k in anys))


@dataclass
class QuestionScore:
    question_id: str
    system: str
    category: str
    answerable: bool
    facts_total: int = 0
    facts_covered: int = 0
    derived_total: int = 0
    derived_covered: int = 0
    abstained: bool = False
    atomic_claims: list[str] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    cited_sentences: int = 0
    citations_correct: int = 0
    sentences: int = 0
    attributable_facts: int = 0
    attributed_correctly: int = 0
    seconds: float = 0.0
    llm_calls: int = 0
    internal: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def unsupported(self) -> int:
        return sum(v != "supported" for v in self.verdicts)


def score_deterministic(q: dict, out: SystemOutput) -> QuestionScore:
    s = QuestionScore(
        question_id=q["id"],
        system=out.system,
        category=q["category"],
        answerable=q["answerable"],
        abstained=out.abstained,
        seconds=out.seconds,
        llm_calls=out.llm_calls,
        internal=out.internal,
        error=out.error,
    )
    s.sentences = len(split_sentences(out.answer))
    for fact in q.get("facts", []):
        s.facts_total += 1
        covered = fact_covered(fact, out.answer)
        s.facts_covered += covered
        if fact.get("derived"):
            s.derived_total += 1
            s.derived_covered += covered
        if covered and out.citations:
            cites = [c for c in out.citations if fact_covered(fact, c.sentence)]
            if cites:
                s.attributable_facts += 1
                ok = set(fact.get("sources", []))
                s.attributed_correctly += any(ok & set(c.source_names) for c in cites)
    return s


def _ratio(n: float, d: float) -> float | None:
    return round(n / d, 4) if d else None


def aggregate(scores: list[QuestionScore]) -> dict:
    answerable = [s for s in scores if s.answerable]
    unanswerable = [s for s in scores if not s.answerable]
    claims = sum(len(s.verdicts) for s in scores)
    internal = [s.internal for s in scores if s.internal]
    out = {
        "questions": len(scores),
        "errors": sum(1 for s in scores if s.error),
        "fact_recall": _ratio(
            sum(s.facts_covered for s in answerable), sum(s.facts_total for s in answerable)
        ),
        "question_accuracy": _ratio(
            sum(1 for s in answerable if s.facts_total and s.facts_covered == s.facts_total),
            len(answerable),
        ),
        "derived_fact_recall": _ratio(
            sum(s.derived_covered for s in answerable), sum(s.derived_total for s in answerable)
        ),
        "abstention_accuracy": _ratio(sum(s.abstained for s in unanswerable), len(unanswerable)),
        "false_abstention_rate": _ratio(
            sum(1 for s in answerable if s.abstained and s.facts_covered == 0), len(answerable)
        ),
        "atomic_claims": claims,
        "unsupported_claim_rate": _ratio(sum(s.unsupported for s in scores), claims),
        "contradicted_claims": sum(v == "contradicted" for s in scores for v in s.verdicts),
        "citation_coverage": _ratio(
            sum(s.cited_sentences for s in scores), sum(s.sentences for s in scores)
        ),
        "citation_correctness": _ratio(
            sum(s.citations_correct for s in scores), sum(s.cited_sentences for s in scores)
        ),
        "attribution_accuracy": _ratio(
            sum(s.attributed_correctly for s in scores), sum(s.attributable_facts for s in scores)
        ),
        "mean_seconds": round(sum(s.seconds for s in scores) / len(scores), 2) if scores else None,
    }
    if internal:
        supported = sum(i.get("supported", 0) for i in internal)
        out["provenance_completeness"] = _ratio(
            sum(i.get("provenance_valid", 0) for i in internal), supported
        )
        out["internal_claims_rejected"] = sum(i.get("rejected", 0) for i in internal)
        out["internal_claims_unsupported"] = sum(i.get("unsupported", 0) for i in internal)
    return out
