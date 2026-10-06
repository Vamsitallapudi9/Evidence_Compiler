"""Deterministic extraction and comparison of numbers in text.

Used by the calculation engine (to read a value out of a quoted span) and by the
verifier (to check that every number a claim states is backed by its evidence).
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_SCALES = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "mm": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}

_NUMBER_RE = re.compile(
    r"""
    (?<![\w.])                         # not glued to a word (rejects Q2, H1, v1.2)
    (?P<neg>[-−–]|\()?\s?
    (?P<cur>\$|€|£)?\s?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \)?
    \s?(?P<unit>%|percent\b|pp\b|bn\b|mm\b|million\b|billion\b|thousand\b|[kKmMbB]\b)?
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class ParsedNumber:
    raw: Decimal  # the number as written, sign applied (e.g. 114.0)
    value: Decimal  # scaled to base units (e.g. 114000000)
    unit: str | None  # "%", "USD", "EUR", "GBP" or None
    text: str
    decimals: int
    span: tuple[int, int]


def parse_numbers(text: str, *, skip_years: bool = True) -> list[ParsedNumber]:
    out: list[ParsedNumber] = []
    for m in _NUMBER_RE.finditer(text):
        num_txt = m.group("num").replace(",", "")
        try:
            raw = Decimal(num_txt)
        except InvalidOperation:
            continue
        unit_tok = (m.group("unit") or "").lower()
        cur = m.group("cur")
        if skip_years and not cur and not unit_tok and "." not in num_txt and 1900 <= raw <= 2100:
            continue
        if m.group("neg"):
            raw = -raw
        scale = _SCALES.get(unit_tok, Decimal(1))
        unit: str | None = None
        if unit_tok in ("%", "percent", "pp"):
            unit = "%"
        elif cur:
            unit = {"$": "USD", "€": "EUR", "£": "GBP"}[cur]
        decimals = len(num_txt.split(".")[1]) if "." in num_txt else 0
        out.append(
            ParsedNumber(
                raw=raw,
                value=raw * scale,
                unit=unit,
                text=m.group(0).strip(),
                decimals=decimals,
                span=(m.start(), m.end()),
            )
        )
    return out


def to_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        nums = parse_numbers(value, skip_years=False)
        if len(nums) == 1 and nums[0].text.replace(" ", "") == value.strip().replace(" ", ""):
            return nums[0].value
        try:
            return Decimal(value.replace(",", "").strip())
        except InvalidOperation:
            return None
    return None


def json_number(d: Decimal) -> int | float:
    """Store numbers as JSON-native values so they survive persistence as numbers."""
    return int(d) if d == d.to_integral_value() else float(d)


def approx_equal(stated: ParsedNumber, candidate: Decimal) -> bool:
    """True if ``candidate`` rounds to what the claim states, or is within 0.5%.

    Compares both the scaled value ("$114M" == 114000000) and the raw value
    ("114" == 114) so claims can quote numbers in either form.
    """
    for target in {stated.value, stated.raw}:
        for cand in (candidate, -candidate):
            if target == cand:
                return True
            q = Decimal(1).scaleb(-stated.decimals)
            try:
                if cand.quantize(q) == target.quantize(q):
                    return True
            except InvalidOperation:
                pass
            if target != 0 and abs((cand - target) / target) <= Decimal("0.005"):
                return True
    return False


def normalize_text(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def find_quote(evidence_text: str, quote: str) -> tuple[int, int] | None:
    """Locate ``quote`` in ``evidence_text`` ignoring case/whitespace/typography.

    Returns character offsets into the *original* evidence text, or None.
    """
    if not quote or not quote.strip():
        return None
    target = normalize_text(quote)
    # Build normalized text with a map back to original offsets.
    norm_chars: list[str] = []
    index_map: list[int] = []
    prev_space = True
    for i, ch in enumerate(evidence_text):
        c = normalize_text(ch) if not ch.isspace() else " "
        if c == " ":
            if prev_space:
                continue
            prev_space = True
        else:
            prev_space = False
        for cc in c or " ":
            norm_chars.append(cc)
            index_map.append(i)
    norm = "".join(norm_chars)
    pos = norm.find(target)
    if pos < 0:
        return None
    start = index_map[pos]
    end = index_map[min(pos + len(target) - 1, len(index_map) - 1)] + 1
    return start, end
