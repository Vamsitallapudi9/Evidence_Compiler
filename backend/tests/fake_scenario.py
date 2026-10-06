"""A scripted FakeLLM for the demo question "Why did Q2 revenue decline?".

Handlers read evidence IDs out of the prompt exactly as a real model would, then
return drafts that deliberately include failure cases (a fabricated citation and an
unbacked number) so tests can assert the pipeline catches them.
"""

import re

from evidence_compiler.llm.fake import FakeLLM
from evidence_compiler.pipeline.schemas import (
    CalcInputSpec,
    CalcSpec,
    ClaimDraft,
    CompiledAnswer,
    DraftCitation,
    DraftClaim,
    Entailment,
    HypothesisAssessment,
    QuestionPlan,
    SqlPlan,
    StructuredQuery,
)

EVIDENCE_RE = re.compile(r'<evidence id="([^"]+)"[^>]*>\n(.*?)\n</evidence>', re.S)


def _find(prompt: str, *needles: str) -> str:
    for eid, body in EVIDENCE_RE.findall(prompt):
        if all(n in body for n in needles):
            return eid
    raise AssertionError(f"no evidence containing {needles}")


def plan(prompt, schema):
    return QuestionPlan(
        restated_question="Why did revenue decline from Q1 to Q2 FY2026?",
        sub_questions=[
            "How much did Q2 revenue decline?",
            "Which regions drove the decline?",
            "Which customer segments drove the decline?",
        ],
        search_queries=["total revenue second quarter decrease", "Europe revenue enterprise"],
        hypotheses=["Healthcare customers caused the decline."],
        needs_structured_data=True,
    )


def sql(prompt, schema):
    return SqlPlan(
        queries=[
            StructuredQuery(
                target="tabular",
                purpose="Revenue change by region",
                sql="SELECT region, SUM(CASE WHEN quarter='2026-Q2' THEN revenue_usd ELSE 0 END) - "
                "SUM(CASE WHEN quarter='2026-Q1' THEN revenue_usd ELSE 0 END) AS revenue_change_usd "
                "FROM regional_sales GROUP BY region ORDER BY region",
            ),
            StructuredQuery(
                target="tabular",
                purpose="Total revenue change",
                sql="SELECT SUM(CASE WHEN quarter='2026-Q2' THEN revenue_usd ELSE 0 END) - "
                "SUM(CASE WHEN quarter='2026-Q1' THEN revenue_usd ELSE 0 END) AS total_change_usd "
                "FROM regional_sales",
            ),
            StructuredQuery(
                target="tabular",
                purpose="Revenue change by segment",
                sql="SELECT segment, SUM(CASE WHEN quarter='2026-Q2' THEN revenue_usd ELSE 0 END) - "
                "SUM(CASE WHEN quarter='2026-Q1' THEN revenue_usd ELSE 0 END) AS revenue_change_usd "
                "FROM customer_segments_segments GROUP BY segment ORDER BY segment",
            ),
            StructuredQuery(target="tabular", purpose="Bad query", sql="DROP TABLE regional_sales"),
        ]
    )


def sql_repair(prompt, schema):
    return StructuredQuery(
        target="tabular",
        purpose="Bad query (repaired)",
        sql="SELECT COUNT(*) AS n FROM regional_sales",
    )


def claims(prompt, schema):
    headline = _find(prompt, "a decrease of 8.4%")
    europe = _find(prompt, "region = Europe", "revenue_change_usd")
    total = _find(prompt, "total_change_usd")
    enterprise = _find(prompt, "segment = Enterprise")
    return ClaimDraft(
        claims=[
            DraftClaim(
                text="Q2 revenue declined 8.4% to $114.0 million.",
                claim_type="primary",
                citations=[
                    DraftCitation(
                        evidence_id=headline,
                        quote="was $114.0 million, a decrease of 8.4%",
                    )
                ],
            ),
            DraftClaim(
                text="Europe accounted for approximately 71% of the revenue decline.",
                claim_type="derived",
                citations=[DraftCitation(evidence_id=europe), DraftCitation(evidence_id=total)],
                calculation=CalcSpec(
                    op="share_of_total",
                    inputs=[
                        CalcInputSpec(name="part", evidence_id=europe, field="revenue_change_usd"),
                        CalcInputSpec(name="total", evidence_id=total, field="total_change_usd"),
                    ],
                ),
            ),
            DraftClaim(
                text="Enterprise revenue fell by $6.9 million, the largest drop of any segment.",
                claim_type="derived",
                citations=[DraftCitation(evidence_id=enterprise)],
            ),
            DraftClaim(
                text="Europe appears to be the primary driver of the decline.",
                claim_type="interpretation",
                citations=[DraftCitation(evidence_id=europe)],
            ),
            DraftClaim(  # fabricated citation → must be REJECTED
                text="Revenue declined because of a pricing change.",
                claim_type="primary",
                citations=[DraftCitation(evidence_id="ev_doesnotexist", quote="pricing change")],
            ),
            DraftClaim(  # number not in evidence → must be UNSUPPORTED
                text="Q2 revenue declined 12%.",
                claim_type="primary",
                citations=[DraftCitation(evidence_id=headline, quote="a decrease of 8.4%")],
            ),
        ],
        hypotheses=[
            HypothesisAssessment(
                hypothesis="Healthcare customers caused the decline.",
                verdict="not_supported",
                note="No evidence links healthcare customers to the decline.",
            )
        ],
        gaps=[],
    )


def verify(prompt, schema):
    return Entailment(verdict="supports", note="The cited evidence states this directly.")


def compile_(prompt, schema):
    lines = re.findall(r"^- \[c:([A-Za-z0-9_]+)\] \([^)]*\) (.+)$", prompt, re.M)
    sentences = [f"{text.rstrip('.')} [c:{cid}]." for cid, text in lines]
    sentences.append("Overall the company did 50% worse than peers.")  # unmarked → removed
    return CompiledAnswer(text=" ".join(sentences))


def make_fake() -> FakeLLM:
    return FakeLLM(
        handlers={
            "plan": plan,
            "sql": sql,
            "sql_repair": sql_repair,
            "claims": claims,
            "verify": verify,
            "compile": compile_,
        }
    )
