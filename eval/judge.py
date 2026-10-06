"""LLM judge for metrics that cannot be computed deterministically.

The judge uses separate prompts from the system under test and sees a reference
built from the ground-truth file and the raw corpus, never any system's evidence
selection. Judge bias is a known limitation; see docs/evaluation.md.
"""

import json
from pathlib import Path
from typing import Literal

import pandas as pd
from evidence_compiler.llm.base import LLMClient
from pydantic import BaseModel


class AtomicClaims(BaseModel):
    claims: list[str]


class ClaimVerdict(BaseModel):
    claim: str
    verdict: Literal["supported", "unsupported", "contradicted"]


class ClaimVerdicts(BaseModel):
    verdicts: list[ClaimVerdict]


class CitationVerdict(BaseModel):
    supports: bool


DECOMPOSE = """Split the answer into atomic factual claims: each a single, \
self-contained statement of fact (include numbers exactly as stated). Ignore \
statements that only say information is unavailable or insufficient. Return an empty \
list if there are no factual claims."""

JUDGE_CLAIMS = """You check claims against a reference containing ALL of the source \
data available to the system that wrote them. For each claim:
- "supported": the reference states it or it follows by simple arithmetic from it \
(allow normal rounding).
- "contradicted": the reference says otherwise.
- "unsupported": the reference neither states nor implies it (including causal \
claims the data does not establish).
Judge each claim independently. Return one verdict per claim, in order."""

JUDGE_CITATION = """Decide whether the cited passages, taken together, support the \
sentence (allowing simple arithmetic and rounding). Answer false if the passages are \
unrelated or only partially support it."""


def build_reference(demo_dir: Path, pdf_pages: dict[str, dict[int, str]]) -> str:
    parts = [
        "GROUND TRUTH FACTS (computed from the data):",
        (demo_dir / "ground_truth.json").read_text(),
    ]
    for name, pages in pdf_pages.items():
        for n, text in sorted(pages.items()):
            parts.append(f"\n{name} page {n}:\n{text}")
    parts.append(
        "\nregional_sales.csv:\n" + pd.read_csv(demo_dir / "regional_sales.csv").to_csv(index=False)
    )
    for sheet, df in pd.read_excel(demo_dir / "customer_segments.xlsx", sheet_name=None).items():
        parts.append(f"\ncustomer_segments.xlsx [{sheet}]:\n" + df.to_csv(index=False))
    parts.append(
        "\ncrm (Postgres): tables customers(customer_id, name, region, country, segment, "
        "industry) and contract_events(event_id, customer_id, quarter, event_type, "
        "arr_change_usd). Aggregates are listed in the ground truth (churn_counts, "
        "new_contracts)."
    )
    return "\n".join(parts)


class Judge:
    def __init__(self, llm: LLMClient, reference: str):
        self.llm = llm
        self.reference = reference

    def decompose(self, question: str, answer: str) -> list[str]:
        if not answer.strip():
            return []
        res = self.llm.generate(
            task="judge_decompose",
            system=DECOMPOSE,
            prompt=f"Question: {question}\n\nAnswer: {answer}",
            schema=AtomicClaims,
        )
        return [c for c in res.claims if c.strip()]

    def judge_claims(self, claims: list[str]) -> list[str]:
        if not claims:
            return []
        res = self.llm.generate(
            task="judge_claims",
            system=JUDGE_CLAIMS,
            prompt=f"Reference:\n{self.reference}\n\nClaims:\n"
            + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims)),
            schema=ClaimVerdicts,
        )
        verdicts = [v.verdict for v in res.verdicts]
        if len(verdicts) != len(claims):  # be conservative on malformed judge output
            verdicts = (verdicts + ["unsupported"] * len(claims))[: len(claims)]
        return verdicts

    def citation_supports(self, sentence: str, passages: list[str]) -> bool:
        if not passages:
            return False
        res = self.llm.generate(
            task="judge_citation",
            system=JUDGE_CITATION,
            prompt=f"Sentence: {sentence}\n\nCited passages:\n"
            + "\n".join(f"- {p}" for p in passages),
            schema=CitationVerdict,
        )
        return res.supports


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, default=str)
