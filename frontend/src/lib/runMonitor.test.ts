import { describe, expect, it } from "vitest";
import type { LlmCall, RunHeartbeat, RunOut } from "../api/types";
import {
  callCounts,
  classifyLiveness,
  deriveLiveState,
  isInterrupted,
  livenessText,
  mergeCalls,
  newestInFlight,
  runDisplayStatus,
  runDurationS,
  upsertCall,
} from "./runMonitor";

const base = { status: "running" as const, alive: true, lastActivityS: 5, msSinceContact: 1000 };

describe("classifyLiveness", () => {
  it("is working while alive with recent activity", () => {
    expect(classifyLiveness(base)).toBe("working");
    expect(classifyLiveness({ ...base, lastActivityS: 59.9 })).toBe("working");
    expect(classifyLiveness({ ...base, status: "pending" })).toBe("working");
  });
  it("is slow from 60s and stuck from 180s without activity", () => {
    expect(classifyLiveness({ ...base, lastActivityS: 60 })).toBe("slow");
    expect(classifyLiveness({ ...base, lastActivityS: 179 })).toBe("slow");
    expect(classifyLiveness({ ...base, lastActivityS: 180 })).toBe("stuck");
    expect(classifyLiveness({ ...base, lastActivityS: 900 })).toBe("stuck");
  });
  it("is dead when no worker is executing a running or pending run", () => {
    expect(classifyLiveness({ ...base, alive: false })).toBe("dead");
    expect(classifyLiveness({ ...base, status: "pending", alive: false, lastActivityS: 500 })).toBe("dead");
  });
  it("reports a lost connection after 10s without a heartbeat, over everything else", () => {
    expect(classifyLiveness({ ...base, msSinceContact: 10_000 })).toBe("working");
    expect(classifyLiveness({ ...base, msSinceContact: 10_001 })).toBe("disconnected");
    expect(classifyLiveness({ ...base, alive: false, lastActivityS: 400, msSinceContact: 30_000 })).toBe("disconnected");
    expect(classifyLiveness({ ...base, msSinceContact: null })).toBe("working");
  });
  it("describes each state", () => {
    expect(livenessText("working", 3)).toBe("Working");
    expect(livenessText("slow", 92.7)).toBe("Slow — no new activity for 92s (model calls can take a minute or two)");
    expect(livenessText("stuck", 200)).toBe("Looks stuck — no activity for 200s");
    expect(livenessText("dead", 0)).toBe("Not running — the server is no longer working on this run");
    expect(livenessText("disconnected", 0)).toBe("Lost connection to the server");
  });
});

const call = (id: string, over: Partial<LlmCall> = {}): LlmCall => ({
  id,
  task: "verify",
  label: `Call ${id}`,
  model: "gpt-6-luna",
  status: "running",
  started_at: "2026-10-06T10:00:00Z",
  seconds: null,
  input_tokens: null,
  output_tokens: null,
  reasoning_tokens: null,
  ...over,
});

describe("upsertCall", () => {
  it("appends new calls and replaces existing ones by id in place", () => {
    const a = call("a");
    const b = call("b");
    let calls = upsertCall([], a);
    calls = upsertCall(calls, b);
    expect(calls.map((c) => c.id)).toEqual(["a", "b"]);
    const aDone = call("a", { status: "ok", seconds: 4.2, input_tokens: 100, output_tokens: 20 });
    calls = upsertCall(calls, aDone);
    expect(calls).toEqual([aDone, b]);
  });
  it("never lets a replayed start overwrite a finished call", () => {
    const done = call("a", { status: "error", seconds: 1, error: "boom" });
    const calls = [done];
    expect(upsertCall(calls, call("a"))).toBe(calls);
  });
  it("merges live updates over the polled log and orders by start time", () => {
    const polled = [call("b", { started_at: "2026-10-06T10:00:05Z" }), call("a", { status: "ok", seconds: 2 })];
    const live = [call("c", { started_at: "2026-10-06T10:00:09Z" }), call("b", { status: "ok", seconds: 3, started_at: "2026-10-06T10:00:05Z" })];
    const merged = mergeCalls(polled, live);
    expect(merged.map((c) => `${c.id}:${c.status}`)).toEqual(["a:ok", "b:ok", "c:running"]);
    expect(newestInFlight(merged)?.id).toBe("c");
    expect(newestInFlight([call("x", { status: "ok" })])).toBeNull();
  });
});

describe("callCounts", () => {
  it("derives done / running / failed from usage totals", () => {
    const usage = {
      provider: "openai", model: "m", calls: 15, in_flight: 2, failed_calls: 1, cache_hits: 0,
      input_tokens: 0, output_tokens: 0, reasoning_tokens: 0, cached_input_tokens: 0, est_cost_usd: null,
    };
    expect(callCounts(usage, [])).toEqual({ done: 12, running: 2, failed: 1 });
  });
  it("falls back to the call log", () => {
    const calls = [call("a", { status: "ok" }), call("b", { status: "error" }), call("c"), call("d", { status: "cached" })];
    expect(callCounts(null, calls)).toEqual({ done: 2, running: 1, failed: 1 });
  });
});

const run: RunOut = {
  id: "run_1",
  question: "Q",
  status: "running",
  created_at: "2026-10-06T10:00:00Z",
  events: [{ stage: "retrieve", message: "Retrieved 4 passages", data: {}, ts: "2026-10-06T10:00:10Z" }],
  alive: true,
  usage: null,
};
const t0 = Date.parse("2026-10-06T10:00:00Z");

describe("deriveLiveState", () => {
  const heartbeat: RunHeartbeat = {
    run_id: "run_1", status: "running", alive: true, elapsed_s: 30, last_activity_s: 50, current: "Verifying claim 3 of 20",
    usage: { provider: "openai", model: "m", calls: 3, in_flight: 1, failed_calls: 0, cache_hits: 0, input_tokens: 10, output_tokens: 2, reasoning_tokens: 0, cached_input_tokens: 0, est_cost_usd: null },
  };
  it("ticks the heartbeat's last activity forward between heartbeats", () => {
    const hb = { ...heartbeat, last_activity_s: 55 };
    const s = deriveLiveState({ run, lastPollAt: t0, heartbeat: hb, lastHeartbeatAt: t0 + 30_000, events: run.events, calls: [], now: t0 + 39_000 });
    expect(s.lastActivityS).toBe(64);
    expect(s.liveness).toBe("slow");
    expect(s.current).toBe("Verifying claim 3 of 20");
    expect(s.usage?.calls).toBe(3);
  });
  it("falls back to event timestamps and polling without heartbeats", () => {
    const s = deriveLiveState({ run, lastPollAt: t0 + 15_000, heartbeat: null, lastHeartbeatAt: null, events: run.events, calls: [], now: t0 + 20_000 });
    expect(s.lastActivityS).toBe(10);
    expect(s.liveness).toBe("working");
    expect(s.current).toBe("Retrieved 4 passages");
  });
  it("detects a lost connection and a dead worker", () => {
    const lost = deriveLiveState({ run, lastPollAt: t0, heartbeat, lastHeartbeatAt: t0 + 1000, events: [], calls: [], now: t0 + 12_000 });
    expect(lost.liveness).toBe("disconnected");
    const dead = deriveLiveState({ run, lastPollAt: t0, heartbeat: { ...heartbeat, alive: false }, lastHeartbeatAt: t0 + 1000, events: [], calls: [], now: t0 + 2000 });
    expect(dead.liveness).toBe("dead");
  });
});

describe("run status", () => {
  it("recognizes interrupted runs", () => {
    expect(isInterrupted("failed", "Interrupted: server restarted")).toBe(true);
    expect(isInterrupted("failed", "LLMError: timeout")).toBe(false);
    expect(isInterrupted("cancelled", "Interrupted: x")).toBe(false);
    expect(runDisplayStatus("failed", "Interrupted: x")).toBe("interrupted");
    expect(runDisplayStatus("cancelled", null)).toBe("cancelled");
  });
  it("measures a finished run up to its last event or call end", () => {
    const calls = [call("a", { status: "ok", started_at: "2026-10-06T10:01:00Z", seconds: 32 })];
    expect(runDurationS(run, calls)).toBe(92);
    expect(runDurationS({ ...run, events: [] }, [])).toBeNull();
  });
});
