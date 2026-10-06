"""Structured-output schemas for each LLM step.

These are the *only* shapes model output can take. Note what is absent: there is no
way to return evidence text or a computed number as a fact — claims can only cite
evidence IDs, quote spans of existing evidence, and request deterministic operations.
"""

from typing import Literal

from pydantic import BaseModel, Field


class QuestionPlan(BaseModel):
    restated_question: str
    sub_questions: list[str] = Field(description="Atomic sub-questions the answer must cover.")
    search_queries: list[str] = Field(
        description="3-6 short keyword queries for searching documents."
    )
    hypotheses: list[str] = Field(
        description=(
            "2-5 plausible statements a typical answer might assert, including tempting ones, "
            "each phrased as a single declarative sentence to be tested against evidence."
        )
    )
    needs_structured_data: bool


class StructuredQuery(BaseModel):
    target: str = Field(description="The 'target' value of the tables being queried.")
    purpose: str
    sql: str


class SqlPlan(BaseModel):
    queries: list[StructuredQuery]


class CalcInputSpec(BaseModel):
    name: str = Field(description="Input name required by the operation, e.g. 'old' or 'part'.")
    evidence_id: str
    field: str | None = Field(
        default=None, description="Structured field of the evidence holding the number."
    )
    quote: str | None = Field(
        default=None,
        description="Verbatim span of the evidence text containing exactly one number.",
    )


class CalcSpec(BaseModel):
    op: Literal["difference", "pct_change", "ratio", "share_of_total", "sum", "mean"]
    inputs: list[CalcInputSpec]


class DraftCitation(BaseModel):
    evidence_id: str
    quote: str | None = Field(
        default=None,
        description="Exact span copied verbatim from the evidence text that supports the claim.",
    )


class DraftClaim(BaseModel):
    text: str
    claim_type: Literal["primary", "derived", "interpretation"]
    citations: list[DraftCitation]
    calculation: CalcSpec | None = None


class HypothesisAssessment(BaseModel):
    hypothesis: str
    verdict: Literal["supported", "not_supported", "contradicted"]
    note: str


class ClaimDraft(BaseModel):
    claims: list[DraftClaim]
    hypotheses: list[HypothesisAssessment]
    gaps: list[str] = Field(description="Parts of the question the evidence cannot answer.")


class Entailment(BaseModel):
    verdict: Literal["supports", "partial", "does_not_support"]
    note: str


class CompiledAnswer(BaseModel):
    text: str
