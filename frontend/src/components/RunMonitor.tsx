import type { ReactNode } from "react";
import type { LlmCall, RunEvent, RunHeartbeat, RunOut } from "../api/types";
import { formatCost, formatDuration, formatTokens } from "../lib/format";
import { callCounts, deriveLiveState, livenessText, livenessTone, newestInFlight, type Liveness, type Tone } from "../lib/runMonitor";
import { useNow } from "../lib/useNow";
import { Spinner } from "./badges";
import { CallsLog } from "./UsageSummary";

interface Props {
  run: RunOut;
  events: RunEvent[];
  /** Merged call log (run.usage.calls_log + live `llm` events), oldest first. */
  calls: LlmCall[];
  heartbeat: RunHeartbeat | null;
  lastHeartbeatAt: number | null;
  /** When the run query last succeeded (ms epoch). */
  lastPollAt: number | null;
  onCancel: () => void;
  cancelling: boolean;
  cancelError?: string | null;
  onRunAgain?: () => void;
  runAgainPending?: boolean;
  runAgainError?: string | null;
  /** Fixed clock for tests; otherwise ticks every second. */
  now?: number;
}

const TONE_FRAME: Record<Tone, string> = {
  ok: "border-zinc-200 bg-white",
  warn: "border-amber-300 bg-amber-50/50",
  bad: "border-red-300 bg-red-50/50",
};

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-emerald-800",
  warn: "text-amber-800",
  bad: "text-red-800",
};

const HINTS: Partial<Record<Liveness, string>> = {
  stuck: "You can cancel it and run it again.",
  dead: "It was probably interrupted (for example by a server restart). Run it again to start over.",
  disconnected: "Retrying… check that the API server is still running.",
};

function LivenessDot({ state }: { state: Liveness }) {
  if (state === "working") {
    return (
      <span aria-hidden="true" className="relative flex size-2.5 shrink-0">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex size-2.5 rounded-full bg-emerald-500" />
      </span>
    );
  }
  const color = state === "slow" ? "bg-amber-500" : "bg-red-500";
  return <span aria-hidden="true" className={`inline-flex size-2.5 shrink-0 rounded-full ${color}`} />;
}

function Tile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="bg-white px-3 py-2">
      <dt className="text-[11px] text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-base font-semibold text-zinc-900 tabular-nums">{value}</dd>
      {sub ? <dd className="text-[11px] text-zinc-500">{sub}</dd> : null}
    </div>
  );
}

/** Live view of an in-progress run: liveness, current activity, token/call stats and the model-call log. */
export function RunMonitor(props: Props) {
  const { run, events, calls, heartbeat, lastHeartbeatAt, lastPollAt } = props;
  const ticking = useNow(1000, props.now === undefined);
  const now = props.now ?? ticking;

  const live = deriveLiveState({ run, lastPollAt, heartbeat, lastHeartbeatAt, events, calls, now });
  const tone = livenessTone(live.liveness);
  const usage = live.usage;
  const counts = callCounts(usage, calls);
  const inFlight = newestInFlight(calls);
  const created = Date.parse(run.created_at);
  const elapsedS = Number.isNaN(created) ? (heartbeat?.elapsed_s ?? 0) : (now - created) / 1000;
  const callStarted = inFlight ? Date.parse(inFlight.started_at) : NaN;
  const working = live.liveness === "working" || live.liveness === "slow" || live.liveness === "stuck";
  const reasoning = usage?.reasoning_tokens ?? 0;
  const hasCost = usage?.est_cost_usd != null;
  const showRunAgain = Boolean(props.onRunAgain) && (live.liveness === "stuck" || live.liveness === "dead");
  const hint = HINTS[live.liveness];

  return (
    <section aria-label="Run monitor" className={`rounded-lg border p-4 ${TONE_FRAME[tone]}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p role="status" aria-live="polite" className={`flex items-center gap-2 text-sm font-semibold ${TONE_TEXT[tone]}`}>
            <LivenessDot state={live.liveness} />
            {livenessText(live.liveness, live.lastActivityS)}
          </p>
          {hint ? <p className="mt-0.5 pl-4.5 text-xs text-zinc-600">{hint}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {showRunAgain ? (
            <button type="button" className="btn-ghost py-1" onClick={props.onRunAgain} disabled={props.runAgainPending}>
              {props.runAgainPending ? <Spinner /> : null}
              Run again
            </button>
          ) : null}
          <button
            type="button"
            className="btn-ghost py-1 text-red-700 hover:border-red-300 hover:bg-red-50"
            onClick={props.onCancel}
            disabled={props.cancelling}
          >
            {props.cancelling ? <Spinner /> : null}
            {props.cancelling ? "Cancelling…" : "Cancel run"}
          </button>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 text-sm text-zinc-700">
        {working ? <Spinner /> : <span aria-hidden="true" className="inline-block size-3.5 shrink-0 rounded-full border-2 border-zinc-300" />}
        <span className="min-w-0 flex-1 truncate" title={live.current ?? undefined}>
          {live.current ?? (run.status === "pending" ? "Waiting to start…" : "Working…")}
        </span>
        {inFlight && !Number.isNaN(callStarted) && live.liveness !== "dead" ? (
          <span className="shrink-0 font-mono text-xs text-zinc-500 tabular-nums">
            Waiting for {inFlight.model} · {formatDuration((now - callStarted) / 1000)}
          </span>
        ) : null}
      </div>
      {props.cancelling ? (
        <p className="mt-1 pl-5.5 text-xs text-zinc-500">Cancelling at the next step; an in-flight model call may finish first.</p>
      ) : null}

      <dl
        className={`mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-zinc-200 bg-zinc-200 ${
          hasCost ? "sm:grid-cols-5" : "sm:grid-cols-4"
        }`}
      >
        <Tile label="Input tokens" value={formatTokens(usage?.input_tokens ?? 0)} />
        <Tile
          label="Output tokens"
          value={formatTokens(usage?.output_tokens ?? 0)}
          sub={reasoning > 0 ? `incl. ${formatTokens(reasoning)} reasoning` : undefined}
        />
        <Tile
          label="LLM calls"
          value={
            <>
              {counts.done} done
              {counts.running ? <span className="font-normal text-sky-700"> · {counts.running} running</span> : null}
            </>
          }
          sub={counts.failed > 0 ? <span className="font-medium text-red-700">{counts.failed} failed</span> : undefined}
        />
        <Tile label="Elapsed" value={formatDuration(elapsedS)} />
        {hasCost ? <Tile label="Est. cost" value={formatCost(usage?.est_cost_usd)} sub={usage?.model} /> : null}
      </dl>

      <CallsLog calls={calls} now={now} className="mt-3" />

      {props.cancelError ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          Could not cancel: {props.cancelError}
        </p>
      ) : null}
      {props.runAgainError ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          Could not start a new run: {props.runAgainError}
        </p>
      ) : null}
    </section>
  );
}
