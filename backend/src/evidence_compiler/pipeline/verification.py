"""Turns drafted claims into verified, classified Claim objects.

Deterministic checks run first (citation integrity, verbatim quotes, calculations,
number matching, provenance). Only claims that pass them are sent to the model-based
entailment check, which sees nothing but the claim and the evidence it cites.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from evidence_compiler.calc import CalculationError, InputRef, run_calculation
from evidence_compiler.core.ids import content_id
from evidence_compiler.core.invariants import GraphValidator
from evidence_compiler.core.models import (
    Calculation,
    CheckResult,
    Claim,
    ClaimStatus,
    ClaimType,
    EvidenceItem,
    EvidenceLink,
    EvidenceOrigin,
    Relation,
    Source,
)
from evidence_compiler.core.numbers import approx_equal, find_quote, parse_numbers, to_decimal
from evidence_compiler.pipeline.schemas import DraftClaim, Entailment

_INTEGRITY_CHECKS = {"citations_exist", "provenance"}


@dataclass
class ClaimWork:
    """A claim in progress plus everything needed to verify it."""

    claim: Claim
    calc: Calculation | None = None
    calc_evidence: EvidenceItem | None = None
    cited: list[EvidenceItem] = field(default_factory=list)

    def passed_deterministic(self) -> bool:
        return all(c.passed for c in self.claim.checks)


def _check(work: ClaimWork, name: str, passed: bool, detail: str = "") -> bool:
    work.claim.checks.append(CheckResult(name=name, passed=passed, detail=detail))
    return passed


def _candidate_numbers(items: list[EvidenceItem], calc: Calculation | None) -> list[Decimal]:
    out: list[Decimal] = []
    for item in items:
        out.extend(n.value for n in parse_numbers(item.text, skip_years=False))
        out.extend(n.raw for n in parse_numbers(item.text, skip_years=False))
        for v in item.fields.values():
            d = to_decimal(v)
            if d is not None:
                out.append(d)
    if calc is not None:
        out.append(calc.result)
    return out


def check_draft(
    draft: DraftClaim,
    pool: dict[str, EvidenceItem],
    sources: dict[str, Source],
    *,
    enforce: bool = True,
) -> ClaimWork:
    claim_type = ClaimType(draft.claim_type)
    claim = Claim(
        id=content_id("clm", draft.text, [c.evidence_id for c in draft.citations]),
        text=draft.text.strip(),
        type=claim_type,
        status=ClaimStatus.SUPPORTED,
    )
    work = ClaimWork(claim=claim)

    # 0. A claim's type follows from its evidence, not from the model's label.
    cited_origins = {pool[c.evidence_id].origin for c in draft.citations if c.evidence_id in pool}
    relabel: ClaimType | None = None
    if claim_type == ClaimType.PRIMARY and (
        draft.calculation is not None or cited_origins == {EvidenceOrigin.DERIVED}
    ):
        relabel = ClaimType.DERIVED
    elif (
        claim_type == ClaimType.DERIVED
        and draft.calculation is None
        and cited_origins == {EvidenceOrigin.PRIMARY}
    ):
        relabel = ClaimType.PRIMARY
    if relabel is not None:
        _check(
            work,
            "type_from_evidence",
            True,
            f"labelled {claim_type.value}, reclassified as {relabel.value} from its evidence",
        )
        claim_type = claim.type = relabel

    # 1. Citation integrity: every cited id must be evidence the system actually showed.
    missing = [c.evidence_id for c in draft.citations if c.evidence_id not in pool]
    _check(
        work,
        "citations_exist",
        not missing,
        f"fabricated or unknown evidence ids: {', '.join(missing)}" if missing else "",
    )
    _check(work, "has_citations", bool(draft.citations), "" if draft.citations else "no citations")

    # The claim's type follows from its evidence, not from the model's label.
    origins = {pool[c.evidence_id].origin for c in draft.citations if c.evidence_id in pool}
    inferred = claim_type
    if claim_type == ClaimType.PRIMARY and (
        draft.calculation is not None or origins == {EvidenceOrigin.DERIVED}
    ):
        inferred = ClaimType.DERIVED
    elif (
        claim_type == ClaimType.DERIVED
        and draft.calculation is None
        and origins == {EvidenceOrigin.PRIMARY}
    ):
        inferred = ClaimType.PRIMARY
    if inferred != claim_type:
        _check(
            work,
            "type_from_evidence",
            True,
            f"relabelled {claim_type.value} → {inferred.value} to match the cited evidence",
        )
        claim_type = claim.type = inferred

    relation = {
        ClaimType.PRIMARY: Relation.SUPPORTS,
        ClaimType.DERIVED: Relation.DERIVED_FROM,
        ClaimType.INTERPRETATION: Relation.INFERRED_FROM,
    }[claim_type]

    # 2. Quotes must occur verbatim (modulo whitespace/case) in the cited evidence.
    bad_quotes: list[str] = []
    for cite in draft.citations:
        item = pool.get(cite.evidence_id)
        if item is None:
            continue
        work.cited.append(item)
        span = find_quote(item.text, cite.quote) if cite.quote else None
        is_passage = item.location.kind in ("pdf", "text") or item.metadata.get("passage")
        needs_quote = bool(is_passage) and claim_type == ClaimType.PRIMARY
        if (cite.quote and span is None) or (needs_quote and not cite.quote):
            bad_quotes.append(item.id)
        claim.links.append(
            EvidenceLink(
                evidence_id=item.id,
                relation=relation,
                quote=cite.quote if span else None,
                quote_span=span,
            )
        )
    _check(
        work,
        "quotes_verbatim",
        not bad_quotes,
        f"quote missing or not found in: {', '.join(bad_quotes)}" if bad_quotes else "",
    )

    # 3. Deterministic calculation, if requested (or required).
    if draft.calculation is not None:
        refs = [
            InputRef(name=i.name, evidence_id=i.evidence_id, field=i.field, quote=i.quote)
            for i in draft.calculation.inputs
        ]
        try:
            calc, out = run_calculation(draft.calculation.op, refs, pool)
            work.calc, work.calc_evidence = calc, out
            claim.calculation_id = calc.id
            claim.links.append(EvidenceLink(evidence_id=out.id, relation=Relation.CALCULATED_FROM))
            for inp in calc.inputs:
                if not any(link.evidence_id == inp.evidence_id for link in claim.links):
                    claim.links.append(
                        EvidenceLink(evidence_id=inp.evidence_id, relation=Relation.DEPENDS_ON)
                    )
            _check(work, "calculation", True, calc.formula)
        except CalculationError as exc:
            _check(work, "calculation", False, str(exc))
    elif claim_type == ClaimType.DERIVED and not any(
        i.origin == EvidenceOrigin.DERIVED for i in work.cited
    ):
        _check(work, "calculation", False, "derived claim without a calculation or aggregate")

    # 4. Every number the claim states must be backed by its evidence or calculation.
    candidates = _candidate_numbers(work.cited, work.calc)
    unbacked = [
        n.text for n in parse_numbers(claim.text) if not any(approx_equal(n, c) for c in candidates)
    ]
    _check(
        work,
        "numbers_backed",
        not unbacked,
        f"numbers not found in evidence: {', '.join(unbacked)}" if unbacked else "",
    )

    # 5. Provenance must terminate in source material.
    full_pool = dict(pool)
    if work.calc_evidence is not None:
        full_pool[work.calc_evidence.id] = work.calc_evidence
    problems = GraphValidator(full_pool, sources).claim_violations(claim)
    _check(work, "provenance", not problems, "; ".join(problems))

    if not enforce:  # ablation mode: record checks but do not act on them
        for c in claim.checks:
            c.detail = (c.detail + " (not enforced)").strip()
            c.passed = True
    return work


def classify(work: ClaimWork, entailment: Entailment | None) -> Claim:
    claim = work.claim
    failed = [c for c in claim.checks if not c.passed]
    if entailment is not None:
        claim.entailment = entailment.verdict
        claim.entailment_note = entailment.note

    if any(c.name in _INTEGRITY_CHECKS for c in failed):
        claim.status = ClaimStatus.REJECTED
        claim.type = ClaimType.UNSUPPORTED
        claim.reason = "Integrity check failed: " + "; ".join(
            c.detail for c in failed if c.name in _INTEGRITY_CHECKS
        )
    elif failed:
        claim.status = ClaimStatus.UNSUPPORTED
        claim.type = ClaimType.UNSUPPORTED
        claim.reason = "; ".join(f"{c.name}: {c.detail}" for c in failed)
    elif entailment is None:
        claim.status = ClaimStatus.SUPPORTED
        claim.reason = "Deterministic checks passed (entailment not run)."
    elif entailment.verdict == "supports":
        claim.status = ClaimStatus.SUPPORTED
        claim.reason = "All checks passed and the cited evidence supports the claim."
    elif entailment.verdict == "partial":
        claim.status = ClaimStatus.PARTIAL
        claim.reason = "Evidence only partially supports this claim."
    else:
        claim.status = ClaimStatus.UNSUPPORTED
        claim.type = ClaimType.UNSUPPORTED
        claim.reason = "The cited evidence does not support this claim."
    return claim


def hypothesis_claim(hypothesis: str, verdict: str, note: str) -> Claim:
    status = "contradicted by" if verdict == "contradicted" else "not established by"
    return Claim(
        id=content_id("clm", "hypothesis", hypothesis),
        text=hypothesis.strip(),
        type=ClaimType.UNSUPPORTED,
        status=ClaimStatus.UNSUPPORTED,
        origin="hypothesis",
        reason=f"Tested hypothesis {status} the available evidence.",
        entailment_note=note or None,
    )
