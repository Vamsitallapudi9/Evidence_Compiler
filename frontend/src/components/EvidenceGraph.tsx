import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Answer, ClaimStatus, ClaimType, GraphNode } from "../api/types";
import { CLAIM_STATUS_STYLES, CLAIM_TYPE_STYLES, isProblemStatus } from "../lib/claimStyles";
import { layoutGraph } from "../lib/graphLayout";
import type { InspectorTarget } from "../lib/selection";

interface Props {
  answer: Answer;
  onSelect: (target: InspectorTarget) => void;
}

const NODE_WIDTH = 200;

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  question: "Question",
  claim: "Claim",
  evidence: "Evidence",
  calculation: "Calculation",
  source: "Source",
};

function nodeColors(n: GraphNode, answer: Answer): { bg: string; border: string; dashed: boolean; text: string } {
  switch (n.kind) {
    case "question":
      return { bg: "#18181b", border: "#18181b", dashed: false, text: "#fafafa" };
    case "claim": {
      const type = (n.data.type as ClaimType | undefined) ?? "unsupported";
      const status = (n.data.status as ClaimStatus | undefined) ?? "unsupported";
      const s = CLAIM_TYPE_STYLES[isProblemStatus(status) ? "unsupported" : type] ?? CLAIM_TYPE_STYLES.unsupported;
      return { ...s.node, dashed: isProblemStatus(status), text: "#18181b" };
    }
    case "evidence": {
      const item = answer.evidence[n.id];
      if (item?.security_flags.length) return { bg: "#fef2f2", border: "#dc2626", dashed: true, text: "#18181b" };
      const derived = (n.data.origin ?? item?.origin) === "derived";
      return derived
        ? { bg: "#f0fdfa", border: "#5eead4", dashed: false, text: "#18181b" }
        : { bg: "#eff6ff", border: "#93c5fd", dashed: false, text: "#18181b" };
    }
    case "calculation":
      return { bg: "#f5f3ff", border: "#8b5cf6", dashed: false, text: "#18181b" };
    case "source":
      return { bg: "#fafafa", border: "#a1a1aa", dashed: false, text: "#18181b" };
  }
}

function caption(n: GraphNode, answer: Answer): string {
  if (n.kind === "claim") {
    const type = n.data.type as ClaimType | undefined;
    const status = n.data.status as ClaimStatus | undefined;
    const parts = [type ? CLAIM_TYPE_STYLES[type]?.label : null, status ? CLAIM_STATUS_STYLES[status]?.label : null];
    return `Claim · ${parts.filter(Boolean).join(" · ")}`;
  }
  if (n.kind === "evidence") {
    const item = answer.evidence[n.id];
    const origin = String(n.data.origin ?? item?.origin ?? "");
    const flag = item?.security_flags.length ? " · ⚠ flagged" : "";
    return `Evidence · ${origin}${flag}`;
  }
  if (n.kind === "calculation") return `Calculation · ${String(n.data.op ?? "")}`;
  if (n.kind === "source") return `Source · ${String(n.data.kind ?? "")}`;
  return KIND_LABEL[n.kind] ?? n.kind;
}

export function EvidenceGraph({ answer, onSelect }: Props) {
  const { nodes, edges } = useMemo(() => {
    const g = answer.graph;
    const positions = layoutGraph(g.nodes, g.edges, { columnWidth: NODE_WIDTH + 60, rowHeight: 84 });
    const nodes: Node[] = g.nodes.map((n) => {
      const c = nodeColors(n, answer);
      const pos = positions.get(n.id) ?? { x: 0, y: 0 };
      return {
        id: n.id,
        position: { x: pos.x, y: pos.y },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        connectable: false,
        ariaLabel: `${KIND_LABEL[n.kind] ?? n.kind}: ${n.label}`,
        data: {
          label: (
            <div className="text-left">
              <div className="mb-0.5 text-[9px] font-semibold tracking-wider uppercase opacity-60">{caption(n, answer)}</div>
              <div className="line-clamp-3 text-[11px] leading-snug">{n.label}</div>
            </div>
          ),
        },
        style: {
          width: NODE_WIDTH,
          background: c.bg,
          color: c.text,
          border: `1.5px ${c.dashed ? "dashed" : "solid"} ${c.border}`,
          borderRadius: 8,
          padding: "6px 8px",
          cursor: n.kind === "claim" || n.kind === "evidence" || n.kind === "calculation" ? "pointer" : "default",
        },
      };
    });
    const ids = new Set(g.nodes.map((n) => n.id));
    const edges: Edge[] = g.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e, i) => {
        const contradicts = e.relation === "contradicts";
        const color = contradicts ? "#dc2626" : "#a1a1aa";
        return {
          id: `e${i}-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          label: e.relation.replace(/_/g, " "),
          labelStyle: { fontSize: 9, fill: contradicts ? "#b91c1c" : "#52525b" },
          labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
          labelBgPadding: [3, 2] as [number, number],
          style: { stroke: color, strokeWidth: 1.25, strokeDasharray: contradicts ? "4 3" : undefined },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
        };
      });
    return { nodes, edges };
  }, [answer]);

  const onNodeClick: NodeMouseHandler = (_, node) => {
    const gn = answer.graph.nodes.find((n) => n.id === node.id);
    if (!gn) return;
    if (gn.kind === "claim") onSelect({ kind: "claim", id: gn.id });
    else if (gn.kind === "evidence") onSelect({ kind: "evidence", id: gn.id });
    else if (gn.kind === "calculation") {
      const out = answer.calculations[gn.id]?.output_evidence_id;
      if (out) onSelect({ kind: "evidence", id: out });
    }
  };

  if (!answer.graph.nodes.length) {
    return <p className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500">No graph for this answer.</p>;
  }

  return (
    <div className="h-[640px] overflow-hidden rounded-lg border border-zinc-200 bg-white" aria-label="Evidence graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
      >
        <Background gap={20} color="#e4e4e7" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
