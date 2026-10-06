from pathlib import Path

from evidence_compiler.calc import InputRef, run_calculation
from evidence_compiler.core.invariants import GraphValidator
from evidence_compiler.core.models import (
    CalcLocation,
    Claim,
    ClaimStatus,
    ClaimType,
    Creator,
    EvidenceItem,
    EvidenceLink,
    EvidenceOrigin,
    PdfLocation,
    Relation,
    Source,
    SourceKind,
)

SRC = Source(id="src_a", kind=SourceKind.PDF, name="a.pdf", uri="a.pdf", content_hash="h")


def primary(id_: str, text: str = "Revenue was $10M", **kw) -> EvidenceItem:
    return EvidenceItem(
        id=id_,
        source_ids=["src_a"],
        origin=EvidenceOrigin.PRIMARY,
        creator=Creator.CONNECTOR,
        text=text,
        location=PdfLocation(page=1, char_start=0, char_end=len(text)),
        **kw,
    )


def claim(type_: ClaimType, *links: tuple[str, Relation]) -> Claim:
    return Claim(
        id="clm",
        text="x",
        type=type_,
        status=ClaimStatus.SUPPORTED,
        links=[EvidenceLink(evidence_id=e, relation=r) for e, r in links],
    )


def test_creator_enum_has_no_llm_member():
    assert {c.value for c in Creator} == {"connector", "sql", "calc"}


def test_primary_claim_on_primary_evidence_is_valid():
    v = GraphValidator({"e1": primary("e1")}, {"src_a": SRC})
    assert v.claim_violations(claim(ClaimType.PRIMARY, ("e1", Relation.SUPPORTS))) == []


def test_fabricated_evidence_id_is_a_violation():
    v = GraphValidator({}, {"src_a": SRC})
    problems = v.claim_violations(claim(ClaimType.PRIMARY, ("ev_fake", Relation.SUPPORTS)))
    assert any("does not exist" in p for p in problems)


def test_evidence_from_unknown_source_is_a_violation():
    e = primary("e1")
    e.source_ids = ["src_unknown"]
    problems = GraphValidator({"e1": e}, {"src_a": SRC}).evidence_violations("e1")
    assert any("unknown source" in p for p in problems)


def test_derived_evidence_without_calculation_is_a_violation():
    """Something that *claims* to be derived but has no calculation behind it."""
    fake = EvidenceItem(
        id="d1",
        source_ids=["src_a"],
        origin=EvidenceOrigin.DERIVED,
        creator=Creator.CALC,
        text="model says growth is 14%",
        location=CalcLocation(calculation_id="none"),
    )
    problems = GraphValidator({"d1": fake}, {"src_a": SRC}).evidence_violations("d1")
    assert any("lacks its calculation" in p or "no inputs" in p for p in problems)


def test_calculated_evidence_chain_terminates_in_source():
    pool = {"e1": primary("e1", "Q1 revenue $100M"), "e2": primary("e2", "Q2 revenue $114M")}
    _, out = run_calculation(
        "pct_change",
        [InputRef("old", "e1", quote="$100M"), InputRef("new", "e2", quote="$114M")],
        pool,
    )
    pool[out.id] = out
    v = GraphValidator(pool, {"src_a": SRC})
    assert v.claim_violations(claim(ClaimType.DERIVED, (out.id, Relation.CALCULATED_FROM))) == []


def test_cycles_are_detected():
    a = primary("a")
    calc_a = EvidenceItem(
        id="c1",
        source_ids=["src_a"],
        origin=EvidenceOrigin.DERIVED,
        creator=Creator.CALC,
        text="x",
        location=CalcLocation(calculation_id="k1"),
        calculation_id="k1",
        derived_from=["c2"],
    )
    calc_b = calc_a.model_copy(update={"id": "c2", "derived_from": ["c1"]})
    problems = GraphValidator(
        {"a": a, "c1": calc_a, "c2": calc_b}, {"src_a": SRC}
    ).evidence_violations("c1")
    assert any("cycle" in p for p in problems)


def test_claim_type_requires_matching_evidence():
    v = GraphValidator({"e1": primary("e1")}, {"src_a": SRC})
    assert v.claim_violations(claim(ClaimType.DERIVED, ("e1", Relation.DERIVED_FROM)))
    assert v.claim_violations(claim(ClaimType.INTERPRETATION, ("e1", Relation.SUPPORTS)))


def test_llm_and_pipeline_code_never_construct_evidence():
    """Architectural guard: only connectors, the SQL executor and calc mint evidence."""
    root = Path(__file__).resolve().parents[1] / "src" / "evidence_compiler"
    for package in ("llm", "pipeline", "api"):
        for path in (root / package).rglob("*.py"):
            assert "EvidenceItem(" not in path.read_text(), f"{path} constructs EvidenceItem"
