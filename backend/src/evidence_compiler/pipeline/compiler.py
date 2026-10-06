"""Answer compilation with a deterministic post-check.

The model writes prose from verified claims; this module then enforces that every
sentence carries a valid claim marker and states no number its claims don't contain.
Sentences that fail are removed (and reported), never silently kept.
"""

import re

from evidence_compiler.core.models import Claim, ClaimStatus, ClaimType
from evidence_compiler.core.numbers import approx_equal, parse_numbers

MARKER_RE = re.compile(r"\[c:([A-Za-z0-9_]+)\]")
INSUFFICIENT = "Insufficient evidence available."


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def usable(claims: list[Claim]) -> list[Claim]:
    return [c for c in claims if c.status in (ClaimStatus.SUPPORTED, ClaimStatus.PARTIAL)]


def claims_prompt(question: str, claims: list[Claim], gaps: list[str]) -> str:
    """Claims are numbered [c:1], [c:2]… — short markers models copy reliably."""
    lines = [f"Question: {question}", "", "Verified claims:"]
    for i, c in enumerate(claims, start=1):
        label = c.type.value + (" (partially supported)" if c.status == ClaimStatus.PARTIAL else "")
        lines.append(f"- [c:{i}] ({label}) {c.text}")
    if gaps:
        lines += ["", "Known gaps (state briefly that these could not be established):"]
        lines += [f"- {g}" for g in gaps]
    return "\n".join(lines)


def normalize_markers(text: str) -> str:
    """Move markers written after sentence punctuation ("8.4%. [c:x]") before it."""
    return re.sub(
        r"([.!?])\s*((?:\[c:[A-Za-z0-9_]+\]\s*)+)",
        lambda m: f" {m.group(2).strip()}{m.group(1)} ",
        text,
    ).strip()


_ANY_MARKER_RE = re.compile(r"\[\s*c\s*:\s*([^\]]+)\]", re.IGNORECASE)


def canonicalize_markers(text: str, claims: list[Claim]) -> str:
    """Map [c:3], [c:3, c:5], [c:clm_x] and prefix-less ids to canonical [c:<claim id>]."""
    aliases: dict[str, str] = {}
    for i, c in enumerate(claims, start=1):
        aliases[str(i)] = c.id
        aliases[c.id.lower()] = c.id
        aliases[c.id.removeprefix("clm_").lower()] = c.id

    def repl(m: re.Match) -> str:
        parts = [
            p.strip().lower().removeprefix("c:").strip() for p in re.split(r"[,\s]+", m.group(1))
        ]
        ids = [aliases.get(p, p) for p in parts if p]
        return " ".join(f"[c:{i}]" for i in ids)

    return _ANY_MARKER_RE.sub(repl, text)


def postcheck(text: str, claims: list[Claim]) -> tuple[str, list[str]]:
    text = normalize_markers(canonicalize_markers(text, claims))
    by_id = {c.id: c for c in claims}
    kept: list[str] = []
    warnings: list[str] = []
    for sentence in split_sentences(text):
        ids = MARKER_RE.findall(sentence)
        valid = [i for i in ids if i in by_id]
        if not valid:
            warnings.append(f"Removed sentence without a valid claim marker: {sentence!r}")
            continue
        body = MARKER_RE.sub("", sentence)
        candidates = [
            n.value for i in valid for n in parse_numbers(by_id[i].text, skip_years=False)
        ] + [n.raw for i in valid for n in parse_numbers(by_id[i].text, skip_years=False)]
        stray = [
            n.text for n in parse_numbers(body) if not any(approx_equal(n, c) for c in candidates)
        ]
        if stray:
            warnings.append(
                f"Removed sentence stating numbers not in its claims ({', '.join(stray)}): "
                f"{sentence!r}"
            )
            continue
        # Drop markers that point at unknown claims, keep the sentence.
        for bad in set(ids) - set(valid):
            sentence = sentence.replace(f"[c:{bad}]", "")
        kept.append(re.sub(r"\s+([.,;!?])", r"\1", sentence).strip())
    return " ".join(kept), warnings


def fallback_text(claims: list[Claim]) -> str:
    return " ".join(f"{c.text.rstrip('.')} [c:{c.id}]." for c in claims)


def unsupported_sentences(claims: list[Claim]) -> str:
    hyps = [c for c in claims if c.origin == "hypothesis" and c.type == ClaimType.UNSUPPORTED]
    return " ".join(
        f"The available evidence does not establish that “{c.text.rstrip('.')}” [c:{c.id}]."
        for c in hyps
    )
