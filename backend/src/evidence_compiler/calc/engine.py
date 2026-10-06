"""Deterministic calculation engine.

Resolves each requested input from an existing evidence item — either a structured
field or a number inside a quoted span that must literally occur in the evidence
text — computes the operation in Decimal arithmetic, and mints a DERIVED evidence
item whose provenance points at its inputs.
"""

from dataclasses import dataclass
from decimal import Decimal

from evidence_compiler.calc.operations import OPS, CalculationError
from evidence_compiler.core.ids import content_id
from evidence_compiler.core.models import (
    CalcLocation,
    CalcOp,
    Calculation,
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    ResolvedInput,
)
from evidence_compiler.core.numbers import find_quote, json_number, parse_numbers, to_decimal


@dataclass(frozen=True)
class InputRef:
    name: str
    evidence_id: str
    field: str | None = None
    quote: str | None = None


def _resolve(ref: InputRef, evidence: dict[str, EvidenceItem]) -> ResolvedInput:
    item = evidence.get(ref.evidence_id)
    if item is None:
        raise CalculationError(f"input '{ref.name}': unknown evidence id {ref.evidence_id}")
    if ref.field:
        if ref.field not in item.fields:
            raise CalculationError(
                f"input '{ref.name}': field '{ref.field}' not in evidence {item.id} "
                f"(available: {', '.join(item.fields) or 'none'})"
            )
        value = to_decimal(item.fields[ref.field])
        if value is None:
            raise CalculationError(f"input '{ref.name}': field '{ref.field}' is not numeric")
        unit = item.metadata.get("units", {}).get(ref.field)
        return ResolvedInput(
            name=ref.name, evidence_id=item.id, field=ref.field, value=value, unit=unit
        )
    if ref.quote:
        if find_quote(item.text, ref.quote) is None:
            raise CalculationError(
                f"input '{ref.name}': quote not found verbatim in evidence {item.id}"
            )
        nums = parse_numbers(ref.quote)
        if len(nums) != 1:
            raise CalculationError(
                f"input '{ref.name}': quote must contain exactly one number, found {len(nums)}"
            )
        return ResolvedInput(
            name=ref.name,
            evidence_id=item.id,
            quote=ref.quote,
            value=nums[0].value,
            unit=nums[0].unit,
        )
    # Evidence that carries exactly one numeric field can be referenced directly.
    numeric = {k: to_decimal(v) for k, v in item.fields.items()}
    numeric = {k: v for k, v in numeric.items() if v is not None}
    if len(numeric) == 1:
        ((field, value),) = numeric.items()
        return ResolvedInput(name=ref.name, evidence_id=item.id, field=field, value=value)
    raise CalculationError(f"input '{ref.name}': specify a 'field' or a 'quote'")


def _fmt(d: Decimal) -> str:
    if d == d.to_integral_value() and abs(d) < Decimal("1e15"):
        return f"{int(d):,}"
    return f"{d.normalize():f}"


def run_calculation(
    op: CalcOp | str, refs: list[InputRef], evidence: dict[str, EvidenceItem]
) -> tuple[Calculation, EvidenceItem]:
    op = CalcOp(op)
    spec = OPS[op]
    if not refs:
        raise CalculationError("calculation has no inputs")
    resolved = [_resolve(r, evidence) for r in refs]
    values = {r.name: r.value for r in resolved}
    if len(values) != len(resolved):
        raise CalculationError("input names must be unique")
    if spec.required is not None and set(values) != set(spec.required):
        raise CalculationError(
            f"{op.value} requires inputs {list(spec.required)}, got {sorted(values)}"
        )
    units = {r.unit for r in resolved if r.unit}
    if len(units) > 1:
        raise CalculationError(f"inputs have mismatched units: {sorted(units)}")
    in_unit = units.pop() if units else None

    result = spec.fn(values)
    unit = spec.unit(in_unit)
    expr = spec.formula({r.name: _fmt(r.value) for r in resolved})
    shown = f"{result.quantize(Decimal('0.0001')).normalize():f}"
    formula = f"{expr} = {shown}{'%' if unit == '%' else ''}"

    input_ids = [r.evidence_id for r in resolved]
    calc_id = content_id("calc", op.value, [r.model_dump(mode="json") for r in resolved])
    source_ids = sorted({s for r in resolved for s in evidence[r.evidence_id].source_ids})
    out = EvidenceItem(
        id=content_id("ev", "calc", calc_id),
        source_ids=source_ids,
        origin=EvidenceOrigin.DERIVED,
        creator=Creator.CALC,
        text=f"{op.value}: {formula}",
        fields={"result": json_number(result)},
        location=CalcLocation(calculation_id=calc_id),
        derived_from=list(dict.fromkeys(input_ids)),
        calculation_id=calc_id,
        metadata={"units": {"result": unit}} if unit else {},
    )
    calc = Calculation(
        id=calc_id,
        op=op,
        inputs=resolved,
        result=result,
        unit=unit,
        formula=formula,
        output_evidence_id=out.id,
    )
    return calc, out
