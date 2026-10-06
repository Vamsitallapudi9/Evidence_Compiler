// Sample in-progress run for previewing the run monitor without a backend (`/?mock=1&running=1`).
import type { LlmCall, RunEvent, RunHeartbeat, RunOut, RunUsage } from "../api/types";

const MODEL = "gpt-6-luna";
const PRICE_IN = 1.25 / 1e6; // USD per token (illustrative)
const PRICE_OUT = 10 / 1e6;

type CallSpec = [
  id: string,
  task: string,
  label: string,
  startOffsetS: number,
  status: LlmCall["status"],
  seconds: number | null,
  inTok: number | null,
  outTok: number | null,
  reasoning?: number,
  error?: string,
];

const RUNNING_CALLS: CallSpec[] = [
  ["call_01", "plan", "Planning the analysis", -92, "ok", 3.1, 2140, 412, 256],
  ["call_02", "sql", "Writing SQL for regional_sales", -87, "ok", 4.2, 3880, 298],
  ["call_03", "sql_repair", "Repairing SQL (attempt 1)", -82, "ok", 2.6, 4122, 205],
  ["call_04", "claims", "Drafting claims from 16 evidence items", -72, "ok", 28.4, 9912, 2331, 1024],
  ["call_05", "verify", "Verifying claim 1 of 8", -40, "cached", 0, null, null],
  ["call_06", "verify", "Verifying claim 2 of 8", -39, "ok", 6.1, 1804, 96],
  ["call_07", "verify", "Verifying claim 3 of 8", -38, "error", 2.0, null, null, 0, "429 Too Many Requests: rate limit reached, retrying"],
  ["call_08", "verify", "Verifying claim 3 of 8 (retry)", -34, "ok", 7.4, 1911, 141],
  ["call_09", "verify", "Verifying claim 4 of 8", -30, "ok", 8.8, 2016, 188, 64],
  ["call_10", "verify", "Verifying claim 5 of 8", -23, "running", null, null, null],
  ["call_11", "verify", "Verifying claim 6 of 8", -8, "running", null, null, null],
];

const iso = (ms: number) => new Date(ms).toISOString();

function makeCalls(specs: CallSpec[], at: (offsetS: number) => number): LlmCall[] {
  return specs.map(([id, task, label, off, status, seconds, inTok, outTok, reasoning = 0, error]) => ({
    id,
    task,
    label,
    model: MODEL,
    status,
    started_at: iso(at(off)),
    seconds,
    input_tokens: inTok,
    output_tokens: outTok,
    reasoning_tokens: inTok == null ? null : reasoning,
    error: error ?? null,
  }));
}

export function usageFromCalls(calls: LlmCall[], withLog = false): RunUsage {
  const sum = (f: (c: LlmCall) => number | null) => calls.reduce((n, c) => n + (f(c) ?? 0), 0);
  const input = sum((c) => c.input_tokens);
  const output = sum((c) => c.output_tokens);
  return {
    provider: "openai",
    model: MODEL,
    calls: calls.length,
    in_flight: calls.filter((c) => c.status === "running").length,
    failed_calls: calls.filter((c) => c.status === "error").length,
    cache_hits: calls.filter((c) => c.status === "cached").length,
    input_tokens: input,
    output_tokens: output,
    reasoning_tokens: sum((c) => c.reasoning_tokens),
    cached_input_tokens: 1804,
    est_cost_usd: Math.round((input * PRICE_IN + output * PRICE_OUT) * 10000) / 10000,
    ...(withLog ? { calls_log: calls } : {}),
  };
}

export interface RunningMock {
  run: RunOut;
  calls: LlmCall[];
  events: RunEvent[];
  /** Builds the heartbeat the server would send at `nowMs`. */
  heartbeatAt: (nowMs: number) => RunHeartbeat;
}

/**
 * A run ~95s in, verifying claims with two calls in flight.
 * `staleS` moves everything back so the newest activity was that long ago; `dead` clears `alive`.
 */
export function makeRunningMock({ now, staleS = 0, dead = false }: { now: number; staleS?: number; dead?: boolean }): RunningMock {
  // The newest activity in the sample is the call started 8s ago.
  const shiftS = staleS > 8 ? staleS - 8 : 0;
  const at = (offsetS: number) => now + (offsetS - shiftS) * 1000;
  const createdAt = at(-95);
  const lastActivity = at(-8);

  const calls = makeCalls(RUNNING_CALLS, at);
  const events: RunEvent[] = [
    { stage: "retrieve", message: "Retrieved 12 passages and 4 table rows", data: {}, ts: iso(at(-93)) },
    { stage: "sql", message: "Ran 3 queries over regional_sales (1 repaired)", data: {}, ts: iso(at(-79)) },
    { stage: "claims", message: "Drafted 8 claims", data: {}, ts: iso(at(-43)) },
    { stage: "verify", message: "Verifying 8 claims", data: {}, ts: iso(at(-41)) },
  ];
  const usage = usageFromCalls(calls);
  const run: RunOut = {
    id: "run_mock_live",
    question: "Why did revenue decline in Q2 2026, and which regions drove it?",
    status: "running",
    created_at: iso(createdAt),
    events,
    answer: null,
    alive: !dead,
    usage: { ...usage, calls_log: calls },
  };
  const current = calls.filter((c) => c.status === "running").at(-1)?.label ?? null;
  return {
    run,
    calls,
    events,
    heartbeatAt: (nowMs) => ({
      run_id: run.id,
      status: "running",
      alive: !dead,
      elapsed_s: Math.max(0, (nowMs - createdAt) / 1000),
      last_activity_s: Math.max(0, (nowMs - lastActivity) / 1000),
      current,
      usage,
    }),
  };
}

/** The same run after it finished (all calls resolved), for the post-run usage summary. */
export function makeFinishedCalls(createdAt: string): LlmCall[] {
  const start = Date.parse(createdAt);
  const specs: CallSpec[] = RUNNING_CALLS.map((s) =>
    s[4] === "running" ? [s[0], s[1], s[2], s[3], "ok", 9.3, 2088, 174] : s,
  );
  specs.push(
    ["call_12", "verify", "Verifying claim 7 of 8", -15, "ok", 6.7, 1950, 120],
    ["call_13", "verify", "Verifying claim 8 of 8", -14, "ok", 7.1, 1874, 133],
    ["call_14", "compile", "Compiling the answer", -5, "ok", 4.0, 12410, 1650, 512],
  );
  // Offsets above are relative to the end of a 97s run.
  return makeCalls(specs, (off) => start + (97 + off) * 1000);
}
