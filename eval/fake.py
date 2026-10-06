"""Scripted model for `python -m eval.run --fake`: exercises the harness end to end
without network access. Its outputs are placeholders; the resulting numbers mean nothing."""

import re

from evidence_compiler.llm.fake import FakeLLM
from evidence_compiler.pipeline.schemas import (
    ClaimDraft,
    CompiledAnswer,
    Entailment,
    QuestionPlan,
    SqlPlan,
)

from eval.judge import AtomicClaims, CitationVerdict, ClaimVerdicts
from eval.systems.rag import CitedSentence, RagAnswer, RagCitedAnswer


def _first_passage(prompt: str) -> str:
    m = re.search(r"^\[1\] \([^)]*\) (.+)$", prompt, re.M)
    return m.group(1) if m else "No information."


def make_eval_fake() -> FakeLLM:
    return FakeLLM(
        handlers={
            "plan": lambda p, s: QuestionPlan(
                restated_question="q",
                sub_questions=[],
                search_queries=[],
                hypotheses=[],
                needs_structured_data=False,
            ),
            "sql": lambda p, s: SqlPlan(queries=[]),
            "claims": lambda p, s: ClaimDraft(claims=[], hypotheses=[], gaps=["(fake run)"]),
            "verify": lambda p, s: Entailment(verdict="supports", note="fake"),
            "compile": lambda p, s: CompiledAnswer(text=""),
            "rag_answer": lambda p, s: RagAnswer(answer=_first_passage(p)),
            "rag_cited": lambda p, s: RagCitedAnswer(
                sentences=[CitedSentence(text=_first_passage(p), citations=[1])]
            ),
            "judge_decompose": lambda p, s: AtomicClaims(
                claims=[] if "Answer: Insufficient" in p else ["placeholder claim"]
            ),
            "judge_claims": lambda p, s: ClaimVerdicts(
                verdicts=[
                    {"claim": c, "verdict": "unsupported"}
                    for c in re.findall(r"^\d+\. (.+)$", p, re.M)
                ]
            ),
            "judge_citation": lambda p, s: CitationVerdict(supports=True),
        }
    )
