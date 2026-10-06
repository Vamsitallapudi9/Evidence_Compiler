"""Provenance invariants.

The rule this module enforces: every claim's provenance chain must terminate in
source material. Primary evidence must come from a connector or a SQL lookup against
a registered source; derived evidence must come from the calculation engine or a SQL
aggregate and must point back (transitively) at primary evidence or a source table.
Nothing produced by the LLM may appear anywhere in the chain.
"""

from dataclasses import dataclass, field

from evidence_compiler.core.models import (
    CalcLocation,
    Claim,
    ClaimType,
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    QueryLocation,
    Relation,
    Source,
)

_PRIMARY_CREATORS = {Creator.CONNECTOR, Creator.SQL}
_DERIVED_CREATORS = {Creator.CALC, Creator.SQL}


class ProvenanceError(ValueError):
    pass


@dataclass
class GraphValidator:
    evidence: dict[str, EvidenceItem]
    sources: dict[str, Source]
    _ok_cache: dict[str, list[str]] = field(default_factory=dict)

    def evidence_violations(self, evidence_id: str) -> list[str]:
        return self._check(evidence_id, ())

    def _check(self, evidence_id: str, path: tuple[str, ...]) -> list[str]:
        if evidence_id in path:
            return [f"cycle in provenance: {' -> '.join((*path, evidence_id))}"]
        if evidence_id in self._ok_cache:
            return self._ok_cache[evidence_id]
        item = self.evidence.get(evidence_id)
        if item is None:
            return [f"evidence {evidence_id} does not exist"]

        problems: list[str] = []
        try:
            creator = Creator(item.creator)
        except ValueError:
            return [f"evidence {item.id} has unknown creator {item.creator!r}"]

        if not item.source_ids:
            problems.append(f"evidence {item.id} has no source")
        for sid in item.source_ids:
            if sid not in self.sources:
                problems.append(f"evidence {item.id} references unknown source {sid}")

        if item.origin == EvidenceOrigin.PRIMARY:
            if creator not in _PRIMARY_CREATORS:
                problems.append(f"primary evidence {item.id} created by {creator.value}")
            if item.derived_from:
                problems.append(f"primary evidence {item.id} must not be derived from others")
        elif item.origin == EvidenceOrigin.DERIVED:
            if creator not in _DERIVED_CREATORS:
                problems.append(f"derived evidence {item.id} created by {creator.value}")
            if creator == Creator.CALC:
                if not isinstance(item.location, CalcLocation) or not item.calculation_id:
                    problems.append(f"calculated evidence {item.id} lacks its calculation")
                if not item.derived_from:
                    problems.append(f"calculated evidence {item.id} has no inputs")
                for parent in item.derived_from:
                    problems.extend(self._check(parent, (*path, evidence_id)))
            elif creator == Creator.SQL and not isinstance(item.location, QueryLocation):
                problems.append(f"SQL-derived evidence {item.id} lacks its query")
        else:  # pragma: no cover - enum exhaustiveness
            problems.append(f"evidence {item.id} has invalid origin")

        self._ok_cache[evidence_id] = problems
        return problems

    def claim_violations(self, claim: Claim) -> list[str]:
        problems: list[str] = []
        for link in claim.links:
            problems.extend(self.evidence_violations(link.evidence_id))

        def linked(*relations: Relation) -> list[EvidenceItem]:
            return [
                self.evidence[link.evidence_id]
                for link in claim.links
                if link.relation in relations and link.evidence_id in self.evidence
            ]

        if claim.type == ClaimType.PRIMARY:
            if not any(e.origin == EvidenceOrigin.PRIMARY for e in linked(Relation.SUPPORTS)):
                problems.append("primary claim has no supporting primary evidence")
        elif claim.type == ClaimType.DERIVED:
            derived = linked(Relation.CALCULATED_FROM, Relation.DERIVED_FROM, Relation.SUPPORTS)
            if not any(e.origin == EvidenceOrigin.DERIVED for e in derived):
                problems.append("derived claim has no derived evidence")
        elif claim.type == ClaimType.INTERPRETATION and not linked(Relation.INFERRED_FROM):
            problems.append("interpretation has no evidence it is inferred from")
        return problems

    def assert_valid(self, claim: Claim) -> None:
        problems = self.claim_violations(claim)
        if problems:
            raise ProvenanceError("; ".join(problems))
