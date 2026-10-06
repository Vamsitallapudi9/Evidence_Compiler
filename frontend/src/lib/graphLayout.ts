import type { GraphEdge, GraphNode, GraphNodeKind } from "../api/types";

export interface LayoutOptions {
  columnWidth: number;
  rowHeight: number;
}

export interface Positioned {
  id: string;
  column: number;
  row: number;
  x: number;
  y: number;
}

const DEFAULT_COLUMN: Record<GraphNodeKind, number> = {
  question: 0,
  claim: 1,
  calculation: 2,
  evidence: 3,
  source: 4,
};

/**
 * Deterministic left-to-right layered layout.
 *
 * Columns follow edge direction (longest path from the question), so the flow reads
 * question → claims → calculations/evidence → upstream evidence → sources. Sources are
 * pinned to the last column. Within a column, nodes are ordered by the mean row of
 * their parents (one barycenter pass) with input order as the tie-breaker.
 */
export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  { columnWidth, rowHeight }: LayoutOptions = { columnWidth: 280, rowHeight: 88 },
): Map<string, Positioned> {
  const ids = new Set(nodes.map((n) => n.id));
  const order = new Map(nodes.map((n, i) => [n.id, i]));
  const kindOf = new Map(nodes.map((n) => [n.id, n.kind]));
  const validEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target);

  // Longest-path layering via bounded relaxation (bounded so cycles cannot loop forever).
  // Roots (no incoming edges) start at their kind's default column; everything else is
  // pushed right by its parents.
  const column = new Map<string, number>();
  for (const n of nodes) column.set(n.id, DEFAULT_COLUMN[n.kind] ?? 0);
  const hasIncoming = new Set(validEdges.map((e) => e.target));
  for (const n of nodes) if (hasIncoming.has(n.id)) column.set(n.id, 0);

  for (let pass = 0; pass < nodes.length; pass++) {
    let changed = false;
    for (const e of validEdges) {
      const next = (column.get(e.source) ?? 0) + 1;
      if (next > (column.get(e.target) ?? 0) && next <= nodes.length) {
        column.set(e.target, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  // Pin sources to the rightmost column.
  let maxNonSource = 0;
  for (const n of nodes) if (n.kind !== "source") maxNonSource = Math.max(maxNonSource, column.get(n.id) ?? 0);
  for (const n of nodes) if (n.kind === "source") column.set(n.id, maxNonSource + 1);

  // Compact: remove empty columns.
  const used = [...new Set(column.values())].sort((a, b) => a - b);
  const compact = new Map(used.map((c, i) => [c, i]));
  for (const [id, c] of column) column.set(id, compact.get(c) ?? c);

  // Group by column and order rows.
  const parents = new Map<string, string[]>();
  for (const e of validEdges) {
    if ((column.get(e.source) ?? 0) < (column.get(e.target) ?? 0)) {
      parents.set(e.target, [...(parents.get(e.target) ?? []), e.source]);
    }
  }
  const byColumn = new Map<number, string[]>();
  for (const n of nodes) {
    const c = column.get(n.id) ?? 0;
    byColumn.set(c, [...(byColumn.get(c) ?? []), n.id]);
  }

  const row = new Map<string, number>();
  const columns = [...byColumn.keys()].sort((a, b) => a - b);
  for (const c of columns) {
    const members = byColumn.get(c) ?? [];
    const score = (id: string) => {
      const ps = (parents.get(id) ?? []).filter((p) => row.has(p));
      if (!ps.length) return Number.POSITIVE_INFINITY;
      return ps.reduce((sum, p) => sum + (row.get(p) ?? 0), 0) / ps.length;
    };
    const sorted = [...members].sort((a, b) => {
      const sa = score(a);
      const sb = score(b);
      if (sa !== sb) return sa < sb ? -1 : 1;
      // Keep kinds grouped within mixed columns, then preserve input order.
      const ka = DEFAULT_COLUMN[kindOf.get(a) ?? "evidence"];
      const kb = DEFAULT_COLUMN[kindOf.get(b) ?? "evidence"];
      if (ka !== kb) return ka - kb;
      return (order.get(a) ?? 0) - (order.get(b) ?? 0);
    });
    sorted.forEach((id, i) => row.set(id, i));
    byColumn.set(c, sorted);
  }

  const tallest = Math.max(1, ...[...byColumn.values()].map((m) => m.length));
  const out = new Map<string, Positioned>();
  for (const [c, members] of byColumn) {
    const offset = ((tallest - members.length) * rowHeight) / 2; // vertically center each column
    members.forEach((id, r) => {
      out.set(id, { id, column: c, row: r, x: c * columnWidth, y: offset + r * rowHeight });
    });
  }
  return out;
}
