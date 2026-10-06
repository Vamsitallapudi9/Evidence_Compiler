from decimal import Decimal

import pytest

from evidence_compiler.calc import CalculationError, InputRef, run_calculation
from evidence_compiler.core.models import (
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    PdfLocation,
)
from evidence_compiler.core.numbers import approx_equal, find_quote, parse_numbers


def ev(id_: str, text: str, **fields) -> EvidenceItem:
    return EvidenceItem(
        id=id_,
        source_ids=["src_a"],
        origin=EvidenceOrigin.PRIMARY,
        creator=Creator.CONNECTOR,
        text=text,
        fields=fields,
        location=PdfLocation(page=1, char_start=0, char_end=len(text)),
    )


def test_parse_numbers_scales_and_units():
    nums = parse_numbers("Revenue was $114.0 million, down 8.4% from $124.4M in Q2 2026.")
    assert [(n.value, n.unit) for n in nums] == [
        (Decimal("114000000.0"), "USD"),
        (Decimal("8.4"), "%"),
        (Decimal("124400000.0"), "USD"),
    ]  # "Q2" and the year are not treated as quantities


def test_approx_equal_handles_rounding_and_sign():
    (n,) = parse_numbers("about 71%")
    assert approx_equal(n, Decimal("71.1538"))
    (m,) = parse_numbers("fell $7.4M")
    assert approx_equal(m, Decimal("-7400000"))
    (k,) = parse_numbers("12%")
    assert not approx_equal(k, Decimal("8.36"))


def test_find_quote_is_whitespace_and_case_insensitive():
    text = "Total revenue  was $114.0\nmillion, a decrease of 8.4%."
    span = find_quote(text, "REVENUE was $114.0 million")
    assert span is not None
    assert text[span[0] : span[1]].lower().startswith("revenue")
    assert find_quote(text, "revenue was $115.0 million") is None


def test_calculation_from_fields_and_quotes():
    pool = {
        "e1": ev("e1", "Europe revenue change", revenue_change_usd=-7400000),
        "e2": ev("e2", "Total revenue fell by $10.4 million in the quarter.", change=-10400000),
    }
    calc, out = run_calculation(
        "share_of_total",
        [
            InputRef("part", "e1", field="revenue_change_usd"),
            InputRef("total", "e2", field="change"),
        ],
        pool,
    )
    assert calc.result.quantize(Decimal("0.01")) == Decimal("71.15")
    assert calc.unit == "%"
    assert out.origin == EvidenceOrigin.DERIVED and out.creator == Creator.CALC
    assert out.derived_from == ["e1", "e2"]
    assert "= 71.1538%" in calc.formula
    calc2, _ = run_calculation(
        "difference",
        [
            InputRef("a", "e2", quote="$10.4 million"),
            InputRef("b", "e1", field="revenue_change_usd"),
        ],
        pool,
    )
    assert calc2.result == Decimal("17800000.0")


@pytest.mark.parametrize(
    ("refs", "message"),
    [
        ([InputRef("old", "missing", field="x"), InputRef("new", "e1", field="v")], "unknown"),
        ([InputRef("old", "e1", quote="$999"), InputRef("new", "e1", field="v")], "not found"),
        ([InputRef("a", "e1", field="v"), InputRef("b", "e1", field="v")], "requires inputs"),
        ([InputRef("old", "e1", field="zero"), InputRef("new", "e1", field="v")], "division"),
    ],
)
def test_calculation_rejects_bad_inputs(refs, message):
    pool = {"e1": ev("e1", "value is $5", v=5, zero=0)}
    with pytest.raises(CalculationError, match=message):
        run_calculation("pct_change", refs, pool)
