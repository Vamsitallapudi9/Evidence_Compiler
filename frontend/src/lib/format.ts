import type { CalcOp, FieldValue, Location, SourceKind, SourceOut } from "../api/types";

/**
 * Row indices from the backend are treated as 0-based and displayed 1-based
 * ("row 1" is the first data row).
 */
export const ROW_INDEX_BASE = 0;

export function displayRow(rowIndex: number): number {
  return rowIndex - ROW_INDEX_BASE + 1;
}

/** Parses a decimal string; returns null if it is not a finite number. */
export function parseDecimal(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** Plain number formatting with grouping, trimming insignificant zeros. */
export function formatNumber(value: number, maxFractionDigits = 2): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: maxFractionDigits,
  }).format(value);
}

/** "$7.1M", "$1.25B", "-$310K", "$950" (abbreviates at thousands and above). */
export function formatUsd(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const units: [number, string][] = [
    [1e3, "K"],
    [1e6, "M"],
    [1e9, "B"],
    [1e12, "T"],
  ];
  let i = units.findLastIndex(([size]) => abs >= size);
  if (i === -1) return `${sign}$${formatNumber(abs, 2)}`;
  // Move up a unit when rounding would read "1,000K".
  while (i < units.length - 1 && Number((abs / units[i][0]).toFixed(1)) >= 1000) i++;
  const [size, suffix] = units[i];
  const scaled = abs / size;
  return `${sign}$${formatNumber(scaled, scaled < 10 ? 2 : 1)}${suffix}`;
}

/** Formats a decimal string for display according to its unit. */
export function formatValue(value: string | number, unit?: string | null): string {
  const n = parseDecimal(value);
  if (n === null) return String(value);
  const u = unit?.trim();
  if (u === "%") return `${n.toFixed(1)}%`;
  if (u === "USD" || u === "$") return formatUsd(n);
  if (u === "pp") return `${n.toFixed(1)} pp`;
  return u ? `${formatNumber(n, 4)} ${u}` : formatNumber(n, 4);
}

export function formatFieldValue(value: FieldValue): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return formatNumber(value, 4);
  return value;
}

export interface LocationContext {
  /** Pages/sections in the evidence's source, when known. */
  pageCount?: number | null;
  /** Label used for single-section text sources (defaults to "Document"). */
  sourceName?: string | null;
}

/** Short human label for an evidence location. */
export function formatLocation(loc: Location, ctx: LocationContext = {}): string {
  switch (loc.kind) {
    case "text":
      // Multi-section documents are addressed by section; single-section ones (web pages) by name.
      return (ctx.pageCount ?? 0) > 1 || loc.page > 1 ? `Section ${loc.page}` : ctx.sourceName || "Document";
    case "pdf": {
      let s = `Page ${loc.page}`;
      if (loc.table_index != null) s += `, table ${loc.table_index + 1}`;
      if (loc.row_index != null) s += `, row ${displayRow(loc.row_index)}`;
      return s;
    }
    case "table": {
      const where = loc.sheet ? `${loc.sheet} / ${loc.table}` : loc.table;
      return `${where}, row ${displayRow(loc.row_index)}`;
    }
    case "query": {
      const rows = `${loc.row_count} ${loc.row_count === 1 ? "row" : "rows"}`;
      return `SQL result row ${displayRow(loc.row_index)} of ${rows} (${loc.engine})`;
    }
    case "calc":
      return `Calculation ${loc.calculation_id}`;
  }
}

const OP_LABELS: Record<CalcOp, string> = {
  difference: "Difference",
  pct_change: "Percent change",
  ratio: "Ratio",
  share_of_total: "Share of total",
  sum: "Sum",
  mean: "Mean",
};

export function opLabel(op: string): string {
  return OP_LABELS[op as CalcOp] ?? op;
}

const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  pdf: "PDF",
  csv: "CSV",
  xlsx: "XLSX",
  postgres: "PG",
  web: "WEB",
  docx: "DOC",
  text: "TXT",
  huggingface: "HF",
};

export function sourceKindLabel(kind: string): string {
  return SOURCE_KIND_LABELS[kind as SourceKind] ?? kind.toUpperCase();
}

/** Document-like sources: evidence is passages of text that can be viewed page by page / section by section. */
export function isDocumentKind(kind: string): boolean {
  return kind === "pdf" || kind === "web" || kind === "docx" || kind === "text";
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** One-line summary under a source's name in the sources list. */
export function sourceSubtitle(s: Pick<SourceOut, "kind" | "evidence_count" | "tables" | "page_count">): string {
  if (isDocumentKind(s.kind)) {
    const pages = s.page_count
      ? s.kind === "pdf"
        ? ` · ${plural(s.page_count, "page")}`
        : s.page_count > 1
          ? ` · ${plural(s.page_count, "section")}`
          : ""
      : "";
    return `${s.evidence_count} evidence${pages}`;
  }
  const tables = `${plural(s.tables.length, "table")} · queried via SQL`;
  if (s.kind === "huggingface" && s.evidence_count > 0) return `${tables} · ${plural(s.evidence_count, "passage")}`;
  return tables;
}

/** True for absolute http(s) URLs (the only kind we render as links). */
export function isHttpUrl(url: string | null | undefined): url is string {
  return typeof url === "string" && /^https?:\/\/[^\s/]+/i.test(url.trim());
}

/** "https://www.example.com/a/b?x=1" → "example.com/a/b?x=1" (for compact display; keep the full URL in a title). */
export function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/$/, "");
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** "snake_case_name" → "Snake case name". */
export function humanize(s: string): string {
  const spaced = s.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Token counts for stat tiles: "950", "12,345", "1.2M". */
export function formatTokens(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (Math.abs(n) < 1e6) return formatNumber(Math.round(n), 0);
  const m = n / 1e6;
  return `${formatNumber(m, Math.abs(m) < 100 ? 1 : 0)}M`;
}

/** Compact token counts for one-line summaries: "950", "48.2k", "482k", "1.2M". */
export function formatTokensCompact(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs < 1e3) return String(Math.round(n));
  const k = n / 1e3;
  // Roll up to M when rounding would read "1000k".
  if (abs < 1e6 && Math.abs(Number(k.toFixed(Math.abs(k) < 100 ? 1 : 0))) < 1000) {
    return `${formatNumber(k, Math.abs(k) < 100 ? 1 : 0)}k`;
  }
  const m = n / 1e6;
  return `${formatNumber(m, Math.abs(m) < 100 ? 1 : 0)}M`;
}

/** Elapsed time as "0:07", "1:32" or "1:02:03" (floors to whole seconds; negatives read 0:00). */
export function formatDuration(seconds: number | null | undefined): string {
  const total = seconds == null || !Number.isFinite(seconds) ? 0 : Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** Duration of a single model call: "0.8s", "12s", "1:32". */
export function formatCallSeconds(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds < 10) return `${Math.max(0, seconds).toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return formatDuration(seconds);
}

/** Estimated spend: "$0.031", "$0.04", "$0.25", "$12.40", "<$0.001". */
export function formatCost(usd: number | null | undefined): string {
  if (usd == null || !Number.isFinite(usd)) return "—";
  if (usd > 0 && usd < 0.001) return "<$0.001";
  const digits = usd < 0.1 ? 3 : 2;
  return `$${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: digits }).format(usd)}`;
}
