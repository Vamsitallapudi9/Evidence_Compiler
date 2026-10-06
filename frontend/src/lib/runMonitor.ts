// Pure helpers behind the live run monitor: liveness, LLM call bookkeeping, run status labels.
import type { LlmCall, RunEvent, RunHeartbeat, RunOut, RunStatus, RunUsage } from "../api/types";
import { formatCost, formatDuration, formatTokensCompact } from "./format";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** No new activity for this long reads as "slow" (model calls can legitimately take a minute or two). */
export const SLOW_AFTER_S = 60;
/** No new activity for this long reads as "looks stuck". */
export const STUCK_AFTER_S = 180;
/** No heartbeat (or successful poll) for this long reads as "lost connection". */
export const LOST_AFTER_MS = 10_000;

export type Liveness = "working" | "slow" | "stuck" | "dead" | "disconnected";

export interface LivenessInput {
  status: RunStatus;
  /** A worker is actually executing the run. */
  alive: boolean;
  /** Seconds since the last progress event or LLM call start/end. */
  lastActivityS: number;
  /** Milliseconds since we last heard from the server; null if we have not been listening yet. */
  msSinceContact: number | null;
}

export function classifyLiveness({ status, alive, lastActivityS, msSinceContact }: LivenessInput): Liveness {
  // Without fresh data the other signals are stale, so connection loss wins.
  if (msSinceContact !== null && msSinceContact > LOST_AFTER_MS) return "disconnected";
  if ((status === "running" || status === "pending") && !alive) return "dead";
  if (lastActivityS >= STUCK_AFTER_S) return "stuck";
  if (lastActivityS >= SLOW_AFTER_S) return "slow";
  return "working";
}

export function livenessText(state: Liveness, lastActivityS: number): string {
  const n = Math.max(0, Math.floor(lastActivityS));
  switch (state) {
    case "working":
      return "Working";
    case "slow":
      return `Slow — no new activity for ${n}s (model calls can take a minute or two)`;
    case "stuck":
      return `Looks stuck — no activity for ${n}s`;
    case "dead":
      return "Not running — the server is no longer working on this run";
    case "disconnected":
      return "Lost connection to the server";
  }
}

export type Tone = "ok" | "warn" | "bad";

export function livenessTone(state: Liveness): Tone {
  return state === "working" ? "ok" : state === "slow" ? "warn" : "bad";
}

// --- LLM calls -----------------------------------------------------------------------------

/**
 * Inserts or replaces a call by id. A late "running" copy never overwrites a finished one
 * (reconnects may replay the start event after the end event was already seen).
 */
export function upsertCall(calls: LlmCall[], call: LlmCall): LlmCall[] {
  const i = calls.findIndex((c) => c.id === call.id);
  if (i === -1) return [...calls, call];
  const prev = calls[i];
  if (prev.status !== "running" && call.status === "running") return calls;
  const next = calls.slice();
  next[i] = call;
  return next;
}

const startMs = (c: LlmCall) => {
  const t = Date.parse(c.started_at);
  return Number.isNaN(t) ? 0 : t;
};

/** Applies `updates` on top of `base` (upsert by id) and orders by start time, oldest first. */
export function mergeCalls(base: LlmCall[], updates: LlmCall[]): LlmCall[] {
  return updates.reduce(upsertCall, base).toSorted((a, b) => startMs(a) - startMs(b));
}

/** The most recently started call that is still in flight. */
export function newestInFlight(calls: LlmCall[]): LlmCall | null {
  let best: LlmCall | null = null;
  for (const c of calls) if (c.status === "running" && (!best || startMs(c) >= startMs(best))) best = c;
  return best;
}

export interface CallCounts {
  done: number;
  running: number;
  failed: number;
}

/** Done / running / failed counts, from usage totals when available, else from the call log. */
export function callCounts(usage: RunUsage | null | undefined, calls: LlmCall[]): CallCounts {
  if (usage) {
    const running = usage.in_flight;
    const failed = usage.failed_calls;
    return { done: Math.max(0, usage.calls - running - failed), running, failed };
  }
  const running = calls.filter((c) => c.status === "running").length;
  const failed = calls.filter((c) => c.status === "error").length;
  return { done: calls.length - running - failed, running, failed };
}

// --- Live state ----------------------------------------------------------------------------

const ms = (iso: string | null | undefined) => {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
};

/** Latest activity timestamp (ms) we know of from progress events and call starts/ends. */
export function lastActivityAt(createdAt: string, events: RunEvent[], calls: LlmCall[]): number | null {
  let latest = ms(createdAt);
  const bump = (t: number | null) => {
    if (t !== null && (latest === null || t > latest)) latest = t;
  };
  for (const e of events) bump(ms(e.ts));
  for (const c of calls) {
    const s = ms(c.started_at);
    bump(s);
    if (s !== null && c.seconds != null) bump(s + c.seconds * 1000);
  }
  return latest;
}

export interface LiveInput {
  run: RunOut;
  /** When the run query last succeeded (ms epoch), e.g. TanStack's `dataUpdatedAt`. */
  lastPollAt: number | null;
  heartbeat: RunHeartbeat | null;
  lastHeartbeatAt: number | null;
  events: RunEvent[];
  calls: LlmCall[];
  now: number;
}

export interface LiveState {
  status: RunStatus;
  alive: boolean;
  usage: RunUsage | null;
  lastActivityS: number;
  msSinceContact: number | null;
  current: string | null;
  liveness: Liveness;
}

/**
 * Combines the latest heartbeat with the polled run (whichever is fresher) and ticks the
 * "seconds since activity" forward client-side between heartbeats.
 */
export function deriveLiveState({ run, lastPollAt, heartbeat, lastHeartbeatAt, events, calls, now }: LiveInput): LiveState {
  const hb = heartbeat && lastHeartbeatAt !== null ? heartbeat : null;
  const hbFresher = hb !== null && (lastPollAt === null || (lastHeartbeatAt ?? 0) >= lastPollAt);
  const status = hbFresher ? hb.status : run.status;
  // Older backends omit `alive`: assume a worker until told otherwise.
  const alive = hbFresher ? hb.alive : (run.alive ?? true);
  const usage = (hbFresher ? hb.usage : run.usage) ?? hb?.usage ?? run.usage ?? null;

  let lastActivityS: number;
  if (hb) {
    lastActivityS = hb.last_activity_s + Math.max(0, now - (lastHeartbeatAt ?? now)) / 1000;
  } else {
    const at = lastActivityAt(run.created_at, events, calls);
    lastActivityS = at === null ? 0 : Math.max(0, (now - at) / 1000);
  }

  const contacts = [lastHeartbeatAt, lastPollAt].filter((t): t is number => t !== null && t > 0);
  const msSinceContact = contacts.length ? Math.max(0, now - Math.max(...contacts)) : null;

  const inFlight = newestInFlight(calls);
  const current = hb?.current || inFlight?.label || events.at(-1)?.message || null;

  return {
    status,
    alive,
    usage,
    lastActivityS,
    msSinceContact,
    current,
    liveness: classifyLiveness({ status, alive, lastActivityS, msSinceContact }),
  };
}

/** Wall-clock length of a finished run: creation to its last recorded event or call end. */
export function runDurationS(run: Pick<RunOut, "created_at" | "events">, calls: LlmCall[]): number | null {
  const start = ms(run.created_at);
  const end = lastActivityAt(run.created_at, run.events, calls);
  if (start === null || end === null || end <= start) return null;
  return (end - start) / 1000;
}

/** Pieces of the one-line usage summary, e.g. ["gpt-6-luna", "14 calls", "48.2k in / 6.1k out tokens", "1:32", "≈$0.04"]. */
export function usageSummaryParts(usage: RunUsage, durationS: number | null): string[] {
  const parts = [
    usage.model,
    plural(usage.calls, "call"),
    `${formatTokensCompact(usage.input_tokens)} in / ${formatTokensCompact(usage.output_tokens)} out tokens`,
  ];
  if (durationS != null) parts.push(formatDuration(durationS));
  if (usage.est_cost_usd != null) parts.push(`≈${formatCost(usage.est_cost_usd)}`);
  return parts.filter(Boolean);
}

// --- Run status ----------------------------------------------------------------------------

/** A run cut short by a server restart is reported as failed with an "Interrupted:" error. */
export function isInterrupted(status: RunStatus, error: string | null | undefined): boolean {
  return status === "failed" && typeof error === "string" && /^\s*interrupted:/i.test(error);
}

export type RunDisplayStatus = RunStatus | "interrupted";

export function runDisplayStatus(status: RunStatus, error?: string | null): RunDisplayStatus {
  return isInterrupted(status, error) ? "interrupted" : status;
}

export const RUN_STATUS_STYLES: Record<RunDisplayStatus, { label: string; dot: string; badge: string; text: string }> = {
  pending: { label: "Pending", dot: "bg-zinc-300", badge: "bg-zinc-50 text-zinc-600 ring-zinc-200", text: "text-zinc-500" },
  running: { label: "Running", dot: "bg-sky-500 animate-pulse", badge: "bg-sky-50 text-sky-800 ring-sky-200", text: "text-sky-700" },
  done: { label: "Done", dot: "bg-emerald-500", badge: "bg-emerald-50 text-emerald-800 ring-emerald-200", text: "text-emerald-700" },
  failed: { label: "Failed", dot: "bg-red-500", badge: "bg-red-50 text-red-800 ring-red-200", text: "text-red-600" },
  cancelled: {
    label: "Cancelled",
    dot: "bg-white ring-2 ring-inset ring-zinc-400",
    badge: "bg-zinc-100 text-zinc-700 ring-zinc-300",
    text: "text-zinc-500",
  },
  interrupted: { label: "Interrupted", dot: "bg-amber-500", badge: "bg-amber-50 text-amber-800 ring-amber-200", text: "text-amber-700" },
};
