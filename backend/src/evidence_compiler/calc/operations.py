"""The closed set of deterministic operations the calculation engine supports.

The LLM may *request* one of these by name; it never supplies the numbers or the
formula. Adding an operation means adding a function here, nothing else.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, getcontext

from evidence_compiler.core.models import CalcOp

getcontext().prec = 28


class CalculationError(ValueError):
    pass


@dataclass(frozen=True)
class OpSpec:
    required: tuple[str, ...] | None  # named inputs, or None for variadic
    fn: Callable[[dict[str, Decimal]], Decimal]
    formula: Callable[[dict[str, str]], str]
    unit: Callable[[str | None], str | None]  # result unit given the inputs' unit


def _nonzero(x: Decimal, name: str) -> Decimal:
    if x == 0:
        raise CalculationError(f"division by zero: '{name}' is 0")
    return x


def _same(u: str | None) -> str | None:
    return u


def _pct(_: str | None) -> str:
    return "%"


def _ratio(_: str | None) -> None:
    return None


OPS: dict[CalcOp, OpSpec] = {
    CalcOp.DIFFERENCE: OpSpec(
        ("a", "b"),
        lambda v: v["a"] - v["b"],
        lambda s: f"{s['a']} − {s['b']}",
        _same,
    ),
    CalcOp.PCT_CHANGE: OpSpec(
        ("old", "new"),
        lambda v: (v["new"] - v["old"]) / _nonzero(v["old"], "old") * 100,
        lambda s: f"({s['new']} − {s['old']}) / {s['old']} × 100",
        _pct,
    ),
    CalcOp.RATIO: OpSpec(
        ("numerator", "denominator"),
        lambda v: v["numerator"] / _nonzero(v["denominator"], "denominator"),
        lambda s: f"{s['numerator']} / {s['denominator']}",
        _ratio,
    ),
    CalcOp.SHARE_OF_TOTAL: OpSpec(
        ("part", "total"),
        lambda v: v["part"] / _nonzero(v["total"], "total") * 100,
        lambda s: f"{s['part']} / {s['total']} × 100",
        _pct,
    ),
    CalcOp.SUM: OpSpec(
        None,
        lambda v: sum(v.values(), Decimal(0)),
        lambda s: " + ".join(s.values()),
        _same,
    ),
    CalcOp.MEAN: OpSpec(
        None,
        lambda v: sum(v.values(), Decimal(0)) / Decimal(len(v)),
        lambda s: f"({' + '.join(s.values())}) / {len(s)}",
        _same,
    ),
}
