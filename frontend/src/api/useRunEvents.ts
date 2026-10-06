import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { upsertCall } from "../lib/runMonitor";
import { api } from "./client";
import { queryKeys } from "./hooks";
import type { LlmCall, RunEvent, RunHeartbeat } from "./types";

export type StreamState = "idle" | "connecting" | "open" | "done" | "error";

interface StreamSnapshot {
  runId: string | null;
  events: RunEvent[];
  calls: LlmCall[];
  heartbeat: RunHeartbeat | null;
  /** Client clock (ms) when the latest heartbeat arrived. */
  lastHeartbeatAt: number | null;
  state: StreamState;
}

const empty = (runId: string | null, state: StreamState): StreamSnapshot => ({
  runId,
  events: [],
  calls: [],
  heartbeat: null,
  lastHeartbeatAt: null,
  state,
});

export function eventKey(e: RunEvent): string {
  return `${e.ts}|${e.stage}|${e.message}`;
}

function parse<T>(msg: Event): T | null {
  try {
    return JSON.parse((msg as MessageEvent<string>).data) as T;
  } catch {
    return null;
  }
}

/**
 * Subscribes to `GET /api/runs/{id}/events` (SSE) while `enabled`.
 * Collects `progress` events, `llm` call updates (upserted by id) and the latest `heartbeat`;
 * on `done`, refetches the run so the answer loads.
 */
export function useRunEvents(runId: string | null, enabled: boolean) {
  const qc = useQueryClient();
  const [snap, setSnap] = useState<StreamSnapshot>(() => empty(null, "idle"));

  useEffect(() => {
    if (!runId || !enabled) return;

    const source = new EventSource(api.runEventsUrl(runId));
    const seen = new Set<string>();
    // Updates this run's snapshot, starting a fresh one if the run changed.
    const update = (fn: (s: StreamSnapshot) => StreamSnapshot) =>
      setSnap((s) => fn(s.runId === runId ? s : empty(runId, "connecting")));

    source.onopen = () => update((s) => ({ ...s, state: "open" }));

    source.addEventListener("progress", (msg) => {
      const event = parse<RunEvent>(msg);
      if (!event) return;
      const key = eventKey(event);
      if (seen.has(key)) return; // reconnects may replay history
      seen.add(key);
      update((s) => ({ ...s, events: [...s.events, event] }));
    });

    source.addEventListener("llm", (msg) => {
      const call = parse<LlmCall>(msg);
      if (!call?.id) return;
      update((s) => {
        const calls = upsertCall(s.calls, call);
        return calls === s.calls ? s : { ...s, calls };
      });
    });

    source.addEventListener("heartbeat", (msg) => {
      const heartbeat = parse<RunHeartbeat>(msg);
      if (!heartbeat) return;
      const at = Date.now();
      update((s) => ({ ...s, heartbeat, lastHeartbeatAt: at }));
    });

    source.addEventListener("done", () => {
      source.close();
      update((s) => ({ ...s, state: "done" }));
      void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void qc.invalidateQueries({ queryKey: queryKeys.runs });
    });

    source.onerror = () => {
      // EventSource retries on its own unless the connection was closed for good.
      if (source.readyState === EventSource.CLOSED) {
        update((s) => ({ ...s, state: "error" }));
        void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
      }
    };

    return () => source.close();
  }, [runId, enabled, qc]);

  const current = snap.runId === runId;
  const idle: StreamState = runId && enabled ? "connecting" : "idle";
  return {
    events: current ? snap.events : [],
    calls: current ? snap.calls : [],
    heartbeat: current ? snap.heartbeat : null,
    lastHeartbeatAt: current ? snap.lastHeartbeatAt : null,
    state: current ? snap.state : idle,
  };
}
