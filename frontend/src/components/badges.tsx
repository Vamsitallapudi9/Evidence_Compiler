import type { ReactNode } from "react";
import type { ClaimStatus, ClaimType, EvidenceItem, LlmCall, RunStatus, SourceKind } from "../api/types";
import { CLAIM_STATUS_STYLES, CLAIM_TYPE_STYLES } from "../lib/claimStyles";
import { displayUrl, isHttpUrl, sourceKindLabel } from "../lib/format";
import { RUN_STATUS_STYLES, runDisplayStatus } from "../lib/runMonitor";

const chip = "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap";

export function ClaimTypeBadge({ type, compact = false }: { type: ClaimType; compact?: boolean }) {
  const s = CLAIM_TYPE_STYLES[type];
  return (
    <span className={`${chip} ${s.badge}`} title={s.description}>
      {compact ? s.short : s.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: ClaimStatus }) {
  const s = CLAIM_STATUS_STYLES[status];
  return (
    <span className={`${chip} ${s.badge}`}>
      <span aria-hidden="true">{s.icon}</span>
      {s.label}
    </span>
  );
}

export function OriginBadge({ origin, creator }: Pick<EvidenceItem, "origin" | "creator">) {
  const primary = origin === "primary";
  const via = creator === "sql" ? "SQL" : creator === "calc" ? "calc" : null;
  return (
    <span
      className={`${chip} ${primary ? "bg-blue-50 text-blue-800 ring-blue-200" : "bg-teal-50 text-teal-800 ring-teal-200"}`}
      title={primary ? "Primary evidence: read directly from a source" : "Derived evidence: produced by SQL or a calculation"}
    >
      {primary ? "Primary" : "Derived"}
      {!primary && via ? <span className="opacity-70">· {via}</span> : null}
    </span>
  );
}

const KIND_STYLES: Record<SourceKind, string> = {
  pdf: "bg-red-50 text-red-800 ring-red-200",
  csv: "bg-green-50 text-green-800 ring-green-200",
  xlsx: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  postgres: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  web: "bg-sky-50 text-sky-800 ring-sky-200",
  docx: "bg-blue-50 text-blue-800 ring-blue-200",
  text: "bg-stone-50 text-stone-700 ring-stone-200",
  huggingface: "bg-amber-50 text-amber-800 ring-amber-200",
};

export function SourceKindBadge({ kind }: { kind: string }) {
  const style = KIND_STYLES[kind as SourceKind] ?? "bg-zinc-50 text-zinc-700 ring-zinc-200";
  return (
    <span className={`${chip} w-11 justify-center font-mono text-[10px] tracking-wide ${style}`} aria-label={`${kind} source`}>
      {sourceKindLabel(kind)}
    </span>
  );
}

/** Compact, truncated link to an external page; the full URL is in the tooltip. */
export function ExternalLink({ href, className = "" }: { href: string; className?: string }) {
  if (!isHttpUrl(href)) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={href}
      className={`inline-flex max-w-full min-w-0 items-center gap-0.5 text-[11px] text-zinc-500 underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 hover:decoration-zinc-500 ${className}`}
    >
      <span className="truncate">{displayUrl(href)}</span>
      <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3 shrink-0">
        <path d="M6.22 8.72a.75.75 0 0 0 1.06 1.06l5.22-5.22v1.69a.75.75 0 0 0 1.5 0v-3.5a.75.75 0 0 0-.75-.75h-3.5a.75.75 0 0 0 0 1.5h1.69L6.22 8.72Z" />
        <path d="M3.5 6.75c0-.69.56-1.25 1.25-1.25H7A.75.75 0 0 0 7 4H4.75A2.75 2.75 0 0 0 2 6.75v4.5A2.75 2.75 0 0 0 4.75 14h4.5A2.75 2.75 0 0 0 12 11.25V9a.75.75 0 0 0-1.5 0v2.25c0 .69-.56 1.25-1.25 1.25h-4.5c-.69 0-1.25-.56-1.25-1.25v-4.5Z" />
      </svg>
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

export function WarningBadge({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className={`${chip} bg-red-50 text-red-800 ring-red-200`} title={title}>
      <span aria-hidden="true">⚠</span>
      {children}
    </span>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-3.5 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700 ${className}`}
    />
  );
}

/** Run status chip; failed runs whose error starts with "Interrupted:" read as "Interrupted" (amber). */
export function RunStatusBadge({ status, error }: { status: RunStatus; error?: string | null }) {
  const s = RUN_STATUS_STYLES[runDisplayStatus(status, error)] ?? RUN_STATUS_STYLES.pending;
  return (
    <span className={`${chip} ${s.badge}`}>
      <span aria-hidden="true" className={`inline-block size-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

const CALL_STATUS_LABELS: Record<LlmCall["status"], string> = {
  running: "In progress",
  ok: "Done",
  error: "Failed",
  cached: "Served from cache",
};

/** Spinner / check / cross / cache icon for one model call. */
export function CallStatusIcon({ status }: { status: LlmCall["status"] }) {
  const label = CALL_STATUS_LABELS[status] ?? status;
  let icon: ReactNode;
  if (status === "running") icon = <Spinner />;
  else if (status === "ok")
    icon = (
      <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3.5 text-emerald-600">
        <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
      </svg>
    );
  else if (status === "error")
    icon = (
      <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3.5 text-red-600">
        <path d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z" />
      </svg>
    );
  else
    icon = (
      <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3.5 text-violet-600">
        <path d="M9.58 1.077a.75.75 0 0 1 .405.82L9.165 6h4.085a.75.75 0 0 1 .567 1.241l-6.5 7.5a.75.75 0 0 1-1.302-.638L6.835 10H2.75a.75.75 0 0 1-.567-1.241l6.5-7.5a.75.75 0 0 1 .897-.182Z" />
      </svg>
    );
  return (
    <span className="inline-flex size-4 shrink-0 items-center justify-center" title={label}>
      {icon}
      <span className="sr-only">{label}</span>
    </span>
  );
}
