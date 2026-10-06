import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode } from "../api/types";
import { sampleAnswer } from "../mocks/sampleAnswer";
import { layoutGraph } from "./graphLayout";

const n = (id: string, kind: GraphNode["kind"]): GraphNode => ({ id, kind, label: id, data: {} });

describe("layoutGraph", () => {
  it("lays out question → claim → evidence → source left to right", () => {
    const nodes = [n("q", "question"), n("c1", "claim"), n("e1", "evidence"), n("s1", "source")];
    const edges: GraphEdge[] = [
      { source: "q", target: "c1", relation: "answered_by" },
      { source: "c1", target: "e1", relation: "supports" },
      { source: "e1", target: "s1", relation: "from_source" },
    ];
    const pos = layoutGraph(nodes, edges);
    expect(["q", "c1", "e1", "s1"].map((id) => pos.get(id)?.column)).toEqual([0, 1, 2, 3]);
  });

  it("pins sources to the last column and survives cycles", () => {
    const nodes = [n("q", "question"), n("a", "evidence"), n("b", "evidence"), n("s", "source")];
    const edges: GraphEdge[] = [
      { source: "q", target: "a", relation: "x" },
      { source: "a", target: "b", relation: "x" },
      { source: "b", target: "a", relation: "x" },
      { source: "a", target: "s", relation: "x" },
    ];
    const pos = layoutGraph(nodes, edges);
    const max = Math.max(...[...pos.values()].map((p) => p.column));
    expect(pos.get("s")?.column).toBe(max);
    expect(pos.size).toBe(4);
  });

  it("is deterministic and places every node of the sample graph", () => {
    const { nodes, edges } = sampleAnswer.graph;
    const a = layoutGraph(nodes, edges);
    const b = layoutGraph(nodes, edges);
    expect(a.size).toBe(nodes.length);
    expect([...a.values()]).toEqual([...b.values()]);
    // No two nodes share a position.
    const keys = new Set([...a.values()].map((p) => `${p.x},${p.y}`));
    expect(keys.size).toBe(nodes.length);
  });
});
