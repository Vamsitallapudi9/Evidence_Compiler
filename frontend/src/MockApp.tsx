// Dev-only: renders the AnswerView with sample data, no backend required (`/?mock=1`).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { queryKeys } from "./api/hooks";
import type { RunOut } from "./api/types";
import { AnswerView, type AnswerTabId } from "./components/AnswerView";
import { RunEndedBanner } from "./components/AskView";
import { Layout, ModelChip, StaticIndicator } from "./components/Layout";
import { ProgressTimeline } from "./components/ProgressTimeline";
import { RunMonitor } from "./components/RunMonitor";
import { SourcesPanel } from "./components/SourcesPanel";
import { UsageSummary } from "./components/UsageSummary";
import { runDurationS } from "./lib/runMonitor";
import type { InspectorTarget } from "./lib/selection";
import { sampleAnswer, sampleEvents, samplePages, sampleSources } from "./mocks/sampleAnswer";
import { makeFinishedCalls, makeRunningMock, usageFromCalls } from "./mocks/sampleRun";

// Optional deep links for visual checks: `?mock=1&tab=graph`, `&claim=<id>`, `&evidence=<id>`,
// `&expand=1` (open every disclosure, e.g. the add-source forms).
// Run monitor: `&running=1`, plus `&stale=90` / `&stale=200` (amber / red), `&dead=1` (no worker),
// `&lost=1` (heartbeats stopped). Ended runs: `&ended=cancelled|interrupted|failed`.
function readMockParams(): { tab: AnswerTabId; target: InspectorTarget | null } {
  const p = new URLSearchParams(window.location.search);
  const tab: AnswerTabId = p.get("tab") === "graph" ? "graph" : "answer";
  const claim = p.get("claim");
  const evidence = p.get("evidence");
  const target: InspectorTarget | null = claim
    ? { kind: "claim", id: claim }
    : evidence
      ? { kind: "evidence", id: evidence }
      : null;
  return { tab, target };
}

export default function MockApp() {
  const qc = useQueryClient();
  const [{ tab, target }] = useState(readMockParams);
  // Seed page text so "View page" works without the API, and the sources list so the real
  // SourcesPanel renders (never refetched; add/delete actions will report the backend as offline).
  useState(() => {
    for (const [key, page] of Object.entries(samplePages)) {
      const sourceId = key.slice(0, key.lastIndexOf(":"));
      qc.setQueryData(queryKeys.page(sourceId, page.page), page);
    }
    qc.setQueryDefaults(queryKeys.sources, { staleTime: Infinity, retry: false });
    qc.setQueryData(queryKeys.sources, sampleSources);
    return true;
  });
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("expand") !== "1") return;
    document.querySelectorAll("details").forEach((d) => (d.open = true));
  }, []);

  const params = new URLSearchParams(window.location.search);
  const ended = params.get("ended");
  let main;
  if (params.get("running") === "1") main = <MockRunningRun params={params} />;
  else if (ended === "cancelled" || ended === "interrupted" || ended === "failed") main = <MockEndedRun kind={ended} />;
  else main = <MockAnswer tab={tab} target={target} />;

  return (
    <Layout
      health={
        <div className="flex shrink-0 items-center gap-2">
          <ModelChip provider="openai" model="gpt-6-luna" />
          <StaticIndicator label="Mock data · no backend" />
        </div>
      }
      sidebar={
        <>
          <SourcesPanel />
          <p className="text-xs text-zinc-500">
            Showing sample data. Remove <code className="font-mono">?mock=1</code> to use the live API.
          </p>
        </>
      }
    >
      {main}
    </Layout>
  );
}

const FINISHED_CREATED_AT = "2026-10-05T14:30:35Z";

function Question({ text }: { text: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">Question</p>
      <h2 className="mt-0.5 text-lg font-semibold text-zinc-900">{text}</h2>
    </div>
  );
}

function MockAnswer({ tab, target }: { tab: AnswerTabId; target: InspectorTarget | null }) {
  const calls = useMemo(() => makeFinishedCalls(FINISHED_CREATED_AT), []);
  const usage = useMemo(() => usageFromCalls(calls), [calls]);
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Question text={sampleAnswer.question} />
      <UsageSummary
        usage={usage}
        calls={calls}
        durationS={runDurationS({ created_at: FINISHED_CREATED_AT, events: sampleEvents }, calls)}
      />
      <AnswerView answer={sampleAnswer} initialTab={tab} initialTarget={target} />
      <details className="rounded-lg border border-zinc-200 bg-white">
        <summary className="cursor-pointer px-4 py-2.5 text-sm text-zinc-600 select-none hover:text-zinc-900">
          Compilation log ({sampleEvents.length} steps, illustrative)
        </summary>
        <div className="border-t border-zinc-100 p-1">
          <ProgressTimeline events={sampleEvents} running={false} />
        </div>
      </details>
    </div>
  );
}

/** A live run; heartbeats are simulated every 2s (unless `lost=1`). */
function MockRunningRun({ params }: { params: URLSearchParams }) {
  const [mock] = useState(() =>
    makeRunningMock({ now: Date.now(), staleS: Number(params.get("stale")) || 0, dead: params.get("dead") === "1" }),
  );
  const lost = params.get("lost") === "1";
  const [beat, setBeat] = useState(() => {
    // `lost`: the last heartbeat arrived 14s ago and nothing since.
    const at = lost ? Date.now() - 14_000 : Date.now();
    return { at, heartbeat: mock.heartbeatAt(at) };
  });
  const [cancelling, setCancelling] = useState(false);
  useEffect(() => {
    if (lost) return;
    const id = window.setInterval(() => {
      const at = Date.now();
      setBeat({ at, heartbeat: mock.heartbeatAt(at) });
    }, 2000);
    return () => window.clearInterval(id);
  }, [lost, mock]);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Question text={mock.run.question} />
      <RunMonitor
        run={mock.run}
        events={mock.events}
        calls={mock.calls}
        heartbeat={beat.heartbeat}
        lastHeartbeatAt={beat.at}
        lastPollAt={null}
        onCancel={() => setCancelling(true)}
        cancelling={cancelling}
        onRunAgain={() => {}}
      />
      <ProgressTimeline events={mock.events} running />
    </div>
  );
}

function MockEndedRun({ kind }: { kind: "cancelled" | "interrupted" | "failed" }) {
  const calls = useMemo(() => makeFinishedCalls(FINISHED_CREATED_AT).slice(0, 9), []);
  const usage = useMemo(() => usageFromCalls(calls), [calls]);
  const run: Pick<RunOut, "status" | "error" | "created_at" | "events"> = {
    status: kind === "cancelled" ? "cancelled" : "failed",
    error:
      kind === "interrupted"
        ? "Interrupted: the server restarted while this run was in progress."
        : kind === "failed"
          ? "LLMError: verify call timed out after 120s"
          : null,
    created_at: FINISHED_CREATED_AT,
    events: sampleEvents.slice(0, 4),
  };
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Question text={sampleAnswer.question} />
      <RunEndedBanner run={run} onRunAgain={() => {}} />
      <UsageSummary usage={usage} calls={calls} durationS={runDurationS(run, calls)} />
    </div>
  );
}
