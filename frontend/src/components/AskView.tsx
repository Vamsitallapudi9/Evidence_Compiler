import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, errorMessage } from "../api/client";
import { isTerminal, queryKeys, useCancelRun, useCreateRun, useRun } from "../api/hooks";
import type { RunEvent, RunOut } from "../api/types";
import { eventKey, useRunEvents } from "../api/useRunEvents";
import { formatDateTime } from "../lib/format";
import { isInterrupted, mergeCalls, runDurationS } from "../lib/runMonitor";
import { AnswerView } from "./AnswerView";
import { RunStatusBadge, Spinner } from "./badges";
import { ProgressTimeline } from "./ProgressTimeline";
import { RunMonitor } from "./RunMonitor";
import { UsageSummary } from "./UsageSummary";

interface Props {
  runId: string | null;
  onRunCreated: (runId: string) => void;
  hasSources: boolean;
}

export function AskView({ runId, onRunCreated, hasSources }: Props) {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <QuestionForm onRunCreated={onRunCreated} hasSources={hasSources} />
      {runId ? <RunPanel key={runId} runId={runId} onRunCreated={onRunCreated} /> : <EmptyState hasSources={hasSources} />}
    </div>
  );
}

function QuestionForm({ onRunCreated, hasSources }: { onRunCreated: (id: string) => void; hasSources: boolean }) {
  const [question, setQuestion] = useState("");
  const createRun = useCreateRun();
  const trimmed = question.trim();
  // Linked documents are fetched by the run itself, so no pre-existing source is needed.
  const hasLink = /https?:\/\/\S/i.test(question);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!trimmed || createRun.isPending) return;
    createRun.mutate(trimmed, { onSuccess: ({ run_id }) => onRunCreated(run_id) });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div>
      <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-3 shadow-sm focus-within:border-zinc-400">
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <textarea
          id="question"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question about your sources, e.g. “Why did revenue decline in Q2?”"
          className="block w-full resize-y border-0 bg-transparent px-1 text-[15px] text-zinc-900 placeholder:text-zinc-400 focus:outline-none"
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <p className="text-xs text-zinc-400">
            Enter to ask · Shift+Enter for a new line
            {!hasSources && !hasLink ? <span className="text-amber-700"> · Add a source first for evidence-backed answers</span> : null}
          </p>
          <button type="submit" disabled={!trimmed || createRun.isPending} className="btn-primary">
            {createRun.isPending ? <Spinner className="border-zinc-500 border-t-white" /> : null}
            Ask
          </button>
        </div>
        {createRun.error ? (
          <p role="alert" className="mt-2 text-sm text-red-700">
            Could not start the run: {errorMessage(createRun.error)}
          </p>
        ) : null}
      </form>
      <p className="mt-1.5 px-1 text-xs text-zinc-400">Tip: paste a link (PDF, doc or web page) in your question to answer from it.</p>
    </div>
  );
}

function RunPanel({ runId, onRunCreated }: { runId: string; onRunCreated: (id: string) => void }) {
  const { data: run, error, isLoading, dataUpdatedAt } = useRun(runId);
  const live = Boolean(run) && !isTerminal(run?.status);
  const stream = useRunEvents(runId, live);
  const cancel = useCancelRun(runId);
  const runAgain = useCreateRun();
  const onRunAgain = () => {
    if (run) runAgain.mutate(run.question, { onSuccess: ({ run_id }) => onRunCreated(run_id) });
  };

  // The run's own call log (refreshed by polling) plus live `llm` events, upserted by id.
  const calls = useMemo(() => mergeCalls(run?.usage?.calls_log ?? [], stream.calls), [run?.usage?.calls_log, stream.calls]);

  const events = useMemo(() => {
    const seen = new Set<string>();
    const out: RunEvent[] = [];
    for (const e of [...(run?.events ?? []), ...stream.events]) {
      const k = eventKey(e);
      if (!seen.has(k)) {
        seen.add(k);
        out.push(e);
      }
    }
    return out;
  }, [run?.events, stream.events]);

  // Links in the question are fetched into new sources ("fetch" events): refresh the sources
  // list as each one lands and once more when the run finishes.
  const qc = useQueryClient();
  const fetchCount = events.filter((e) => e.stage === "fetch").length;
  const status = run?.status;
  useEffect(() => {
    if (fetchCount > 0) void qc.invalidateQueries({ queryKey: queryKeys.sources, exact: true });
  }, [fetchCount, status, qc]);

  if (isLoading) {
    return (
      <p className="flex items-center gap-2 text-sm text-zinc-500">
        <Spinner /> Loading run…
      </p>
    );
  }
  if (error || !run) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {notFound ? "This run no longer exists." : `Could not load the run: ${errorMessage(error)}`}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-zinc-500">
          <span>
            Question · {formatDateTime(run.created_at)}
            {stream.state === "error" && live ? " · live updates disconnected, polling…" : ""}
          </span>
          {run.status !== "done" ? <RunStatusBadge status={run.status} error={run.error} /> : null}
        </p>
        <h2 className="mt-0.5 text-lg font-semibold text-zinc-900">{run.question}</h2>
      </div>

      {live ? (
        <>
          <RunMonitor
            run={run}
            events={events}
            calls={calls}
            heartbeat={stream.heartbeat}
            lastHeartbeatAt={stream.lastHeartbeatAt}
            lastPollAt={dataUpdatedAt || null}
            onCancel={() => cancel.mutate()}
            cancelling={cancel.isPending || cancel.isSuccess}
            cancelError={cancel.error ? errorMessage(cancel.error) : null}
            onRunAgain={onRunAgain}
            runAgainPending={runAgain.isPending}
            runAgainError={runAgain.error ? errorMessage(runAgain.error) : null}
          />
          <ProgressTimeline events={events} running />
        </>
      ) : null}

      <RunEndedBanner
        run={run}
        onRunAgain={onRunAgain}
        pending={runAgain.isPending}
        error={runAgain.error ? errorMessage(runAgain.error) : null}
      />

      {!live && run.usage ? <UsageSummary usage={run.usage} calls={calls} durationS={runDurationS(run, calls)} /> : null}

      {run.status === "done" && run.answer ? <AnswerView key={run.answer.run_id} answer={run.answer} /> : null}
      {run.status === "done" && !run.answer ? (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600">
          The run finished but returned no answer.
        </p>
      ) : null}

      {!live && events.length ? (
        <details className="group rounded-lg border border-zinc-200 bg-white">
          <summary className="cursor-pointer px-4 py-2.5 text-sm text-zinc-600 select-none hover:text-zinc-900">
            Compilation log ({events.length} steps)
          </summary>
          <div className="border-t border-zinc-100 p-1">
            <ProgressTimeline events={events} running={false} />
          </div>
        </details>
      ) : null}
    </div>
  );
}

/** Failure / interruption / cancellation notice with a "Run again" action; renders nothing for other statuses. */
export function RunEndedBanner({
  run,
  onRunAgain,
  pending = false,
  error = null,
}: {
  run: Pick<RunOut, "status" | "error">;
  onRunAgain: () => void;
  pending?: boolean;
  error?: string | null;
}) {
  if (run.status !== "failed" && run.status !== "cancelled") return null;
  const interrupted = isInterrupted(run.status, run.error);
  const cancelled = run.status === "cancelled";
  const frame = cancelled
    ? "border-zinc-300 bg-zinc-50"
    : interrupted
      ? "border-amber-300 bg-amber-50"
      : "border-red-200 bg-red-50";
  const title = cancelled ? "The run was cancelled." : interrupted ? "The run was interrupted." : "The run failed.";
  const titleColor = cancelled ? "text-zinc-800" : interrupted ? "text-amber-900" : "text-red-800";
  const reason = (run.error ?? "").replace(/^\s*interrupted:\s*/i, "");
  const detail = interrupted
    ? reason.charAt(0).toUpperCase() + reason.slice(1) || "The server restarted while this run was in progress."
    : cancelled
      ? run.error || "Stopped at your request. The usage below shows how far it got."
      : run.error || "No error details were provided.";

  return (
    <div role={cancelled ? "status" : "alert"} className={`flex flex-wrap items-start justify-between gap-3 rounded-lg border px-4 py-3 ${frame}`}>
      <div className="min-w-0 flex-1">
        <p className={`font-semibold ${titleColor}`}>{title}</p>
        <p
          className={`mt-1 text-sm whitespace-pre-wrap ${
            cancelled ? "text-zinc-600" : interrupted ? "text-amber-800" : "font-mono text-red-700"
          }`}
        >
          {detail}
        </p>
        {error ? <p className="mt-1 text-sm text-red-700">Could not start a new run: {error}</p> : null}
      </div>
      <button type="button" className="btn-primary shrink-0" onClick={onRunAgain} disabled={pending}>
        {pending ? <Spinner className="border-zinc-500 border-t-white" /> : null}
        Run again
      </button>
    </div>
  );
}

function EmptyState({ hasSources }: { hasSources: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center">
      <p className="text-base font-medium text-zinc-800">Ask a question to compile an evidence-backed answer.</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-zinc-500">
        {hasSources
          ? "Every claim in the answer links to source passages, table rows, SQL results or calculations. Anything unsupported is shown explicitly."
          : "Start by adding a file, link, Hugging Face dataset or Postgres connection in the sources panel, or paste a link in your question."}
      </p>
    </div>
  );
}
