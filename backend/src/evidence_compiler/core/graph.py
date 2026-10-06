"""Builds the evidence graph (Question → Claim → Evidence → Calculation → Source)."""

from evidence_compiler.core.models import (
    Calculation,
    Claim,
    EvidenceGraph,
    EvidenceItem,
    GraphEdge,
    GraphNode,
    Source,
)


def _short(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def build_graph(
    question: str,
    claims: list[Claim],
    evidence: dict[str, EvidenceItem],
    calculations: dict[str, Calculation],
    sources: dict[str, Source],
) -> EvidenceGraph:
    g = EvidenceGraph()
    seen: set[str] = set()
    edges: set[tuple[str, str, str]] = set()

    def node(n: GraphNode) -> None:
        if n.id not in seen:
            seen.add(n.id)
            g.nodes.append(n)

    def edge(src: str, dst: str, rel: str) -> None:
        if (src, dst, rel) not in edges:
            edges.add((src, dst, rel))
            g.edges.append(GraphEdge(source=src, target=dst, relation=rel))

    def add_evidence(eid: str) -> None:
        item = evidence.get(eid)
        if item is None or eid in seen:
            return
        node(
            GraphNode(
                id=eid,
                kind="evidence",
                label=_short(item.text),
                data={"origin": item.origin.value, "creator": item.creator.value},
            )
        )
        if item.calculation_id and item.calculation_id in calculations:
            calc = calculations[item.calculation_id]
            node(
                GraphNode(
                    id=calc.id,
                    kind="calculation",
                    label=_short(calc.formula),
                    data={"op": calc.op.value},
                )
            )
            edge(eid, calc.id, "produced_by")
            for inp in calc.inputs:
                add_evidence(inp.evidence_id)
                edge(calc.id, inp.evidence_id, "calculated_from")
        else:
            for parent in item.derived_from:
                add_evidence(parent)
                edge(eid, parent, "derived_from")
            for sid in item.source_ids:
                src = sources.get(sid)
                if src is None:
                    continue
                node(GraphNode(id=sid, kind="source", label=src.name, data={"kind": src.kind}))
                edge(eid, sid, "from_source")

    qid = "question"
    node(GraphNode(id=qid, kind="question", label=_short(question, 120)))
    for claim in claims:
        node(
            GraphNode(
                id=claim.id,
                kind="claim",
                label=_short(claim.text),
                data={"type": claim.type.value, "status": claim.status.value},
            )
        )
        edge(qid, claim.id, "answered_by")
        for link in claim.links:
            add_evidence(link.evidence_id)
            if link.evidence_id in seen:
                edge(claim.id, link.evidence_id, link.relation.value)
    return g
