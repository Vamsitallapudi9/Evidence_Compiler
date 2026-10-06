import { useEffect, useRef, type ReactNode } from "react";
import type { LlmCall, RunUsage } from "../api/types";
import { formatCallSeconds, formatDuration, formatTokens, formatTokensCompact } from "../lib/format";
import { usageSummaryParts } from "../lib/runMonitor";
import { CallStatusIcon } from "./badges";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Seconds a call has taken: its final duration, or (while running) time since it started. */
function callSeconds(c: LlmCall, now: number | undefined): number | null {
  if (c.seconds != null) return c.seconds;
  if (c.status !== "running" || now === undefined) return null;
  const t = Date.parse(c.started_at);
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 1000);
}

function CallRow({ call, now }: { call: LlmCall; now?: number }) {
  const secs = callSeconds(call, now);
  const tokens =
    call.input_tokens == null && call.output_tokens == null
      ? call.status === "cached"
        ? "cached"
        : call.status === "running"
          ? "…"
          : "—"
      : `${formatTokens(call.input_tokens)} → ${formatTokens(call.output_tokens)}`;
  return (
    <li className="flex items-start gap-2 px-3 py-1.5 text-xs">
      <span className="mt-px">
        <CallStatusIcon status={call.status} />
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate ${call.status === "error" ? "text-red-800" : "text-zinc-700"}`} title={call.label}>
          {call.label}
        </span>
        <span className="block truncate text-[11px] text-zinc-400">
          {call.task} · {call.model}
          {call.reasoning_tokens ? ` · ${formatTokens(call.reasoning_tokens)} reasoning` : ""}
        </span>
        {call.error ? (
          <span className="mt-0.5 block font-mono text-[11px] break-words text-red-700" title={call.error}>
            {call.error}
          </span>
        ) : null}
      </span>
      <span className="shrink-0 font-mono text-zinc-500 tabular-nums" title="Input → output tokens">
        {tokens}
      </span>
      <span
        className={`w-12 shrink-0 text-right font-mono tabular-nums ${call.status === "running" ? "text-sky-700" : "text-zinc-500"}`}
        title={call.status === "running" ? "Waiting so far" : "Duration"}
      >
        {call.status === "running" ? formatDuration(secs) : formatCallSeconds(secs)}
      </span>
    </li>
  );
}

interface CallsLogProps {
  calls: LlmCall[];
  /** Clock for running-call timers (ms epoch); without it running calls show no timer. */
  now?: number;
  /** Replaces the default "Model calls (N)" summary. */
  summary?: ReactNode;
  className?: string;
}

/** Collapsible log of model calls, oldest first; follows new rows while scrolled to the bottom. */
export function CallsLog({ calls, now, summary, className = "" }: CallsLogProps) {
  const listRef = useRef<HTMLOListElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = listRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [calls.length]);

  return (
    <details className={`group ${className}`}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-zinc-600 select-none hover:text-zinc-900 [&::-webkit-details-marker]:hidden">
        <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3 shrink-0 transition-transform group-open:rotate-90">
          <path d="M6.22 4.22a.75.75 0 0 1 1.06 0l3.25 3.25a.75.75 0 0 1 0 1.06l-3.25 3.25a.75.75 0 0 1-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 0 1 0-1.06Z" />
        </svg>
        {summary ?? <span className="font-medium">Model calls ({calls.length})</span>}
      </summary>
      {calls.length ? (
        <ol
          ref={listRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          }}
          className="mt-2 max-h-72 divide-y divide-zinc-100 overflow-y-auto rounded-md border border-zinc-200 bg-white"
          aria-label="Model calls"
        >
          {calls.map((c) => (
            <CallRow key={c.id} call={c} now={now} />
          ))}
        </ol>
      ) : (
        <p className="mt-2 text-xs text-zinc-500">No model calls yet.</p>
      )}
    </details>
  );
}

/** Compact one-line usage for a finished run, expanding to its model-call log. */
export function UsageSummary({ usage, calls, durationS }: { usage: RunUsage; calls: LlmCall[]; durationS: number | null }) {
  const line = (
    <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5">
      <span className="text-zinc-600">{usageSummaryParts(usage, durationS).join(" · ")}</span>
      {usage.reasoning_tokens > 0 ? (
        <span className="text-zinc-400">(incl. {formatTokensCompact(usage.reasoning_tokens)} reasoning)</span>
      ) : null}
      {usage.failed_calls > 0 ? <span className="font-medium text-red-700">· {usage.failed_calls} failed</span> : null}
      {usage.cache_hits > 0 ? <span className="text-zinc-400">· {plural(usage.cache_hits, "cache hit")}</span> : null}
    </span>
  );
  return (
    <section aria-label="Model usage" className="rounded-lg border border-zinc-200 bg-white px-4 py-2.5">
      {calls.length ? (
        <CallsLog
          calls={calls}
          summary={
            <>
              {line}
              <span className="ml-auto shrink-0 font-medium text-zinc-500 group-hover:text-zinc-900">Model calls ({calls.length})</span>
            </>
          }
        />
      ) : (
        <p className="text-xs">{line}</p>
      )}
    </section>
  );
}
