import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RunEndedBanner } from "../components/AskView";
import { RunMonitor } from "../components/RunMonitor";
import { UsageSummary } from "../components/UsageSummary";
import { usageSummaryParts } from "../lib/runMonitor";
import { makeFinishedCalls, makeRunningMock, usageFromCalls } from "./sampleRun";

// Drops React's SSR text separators so assertions can match rendered text.
const text = (node: React.ReactNode) => renderToString(node).replace(/<!-- -->/g, "");

const NOW = Date.parse("2026-10-06T10:00:00Z");

function renderMonitor(opts: { staleS?: number; dead?: boolean; heartbeatAgoMs?: number } = {}) {
  const mock = makeRunningMock({ now: NOW, staleS: opts.staleS, dead: opts.dead });
  const at = NOW - (opts.heartbeatAgoMs ?? 1000);
  return text(
    <RunMonitor
      run={mock.run}
      events={mock.events}
      calls={mock.calls}
      heartbeat={mock.heartbeatAt(at)}
      lastHeartbeatAt={at}
      lastPollAt={null}
      onCancel={() => {}}
      cancelling={false}
      onRunAgain={() => {}}
      now={NOW}
    />,
  );
}

describe("run monitor", () => {
  it("shows liveness, the in-flight call timer, stats and the call log", () => {
    const html = renderMonitor();
    expect(html).toContain("Working");
    expect(html).toContain("Verifying claim 6 of 8");
    expect(html).toContain("Waiting for gpt-6-luna · 0:08");
    expect(html).toContain("8 done");
    expect(html).toContain("2 running");
    expect(html).toContain("1 failed");
    expect(html).toContain("incl. 1,344 reasoning");
    expect(html).toContain("1:35"); // elapsed
    expect(html).toContain("Model calls (11)");
    expect(html).toContain("Cancel run");
    expect(html).not.toContain("Run again");
  });
  it("turns amber, then red, as activity goes stale", () => {
    expect(renderMonitor({ staleS: 90 })).toContain("Slow — no new activity for 90s");
    const stuck = renderMonitor({ staleS: 200 });
    expect(stuck).toContain("Looks stuck — no activity for 200s");
    expect(stuck).toContain("Run again");
  });
  it("flags a dead worker and a lost connection", () => {
    expect(renderMonitor({ dead: true })).toContain("Not running — the server is no longer working on this run");
    expect(renderMonitor({ heartbeatAgoMs: 15_000 })).toContain("Lost connection to the server");
  });
});

describe("usage after a run", () => {
  const created = "2026-10-05T14:30:35Z";
  const calls = makeFinishedCalls(created);
  const usage = usageFromCalls(calls);

  it("summarizes usage on one line", () => {
    expect(usageSummaryParts(usage, 92)).toEqual(["gpt-6-luna", "14 calls", "46.2k in / 5.9k out tokens", "1:32", "≈$0.12"]);
    const html = text(<UsageSummary usage={usage} calls={calls} durationS={92} />);
    expect(html).toContain("Model calls (14)");
    expect(html).toContain("1 failed");
  });
  it("labels interrupted and cancelled runs and offers to run again", () => {
    const interrupted = text(
      <RunEndedBanner run={{ status: "failed", error: "Interrupted: server restarted" }} onRunAgain={() => {}} />,
    );
    expect(interrupted).toContain("The run was interrupted.");
    expect(interrupted).toContain("Server restarted");
    expect(interrupted).toContain("Run again");
    const cancelled = renderToString(<RunEndedBanner run={{ status: "cancelled", error: null }} onRunAgain={() => {}} />);
    expect(cancelled).toContain("The run was cancelled.");
    expect(renderToString(<RunEndedBanner run={{ status: "done", error: null }} onRunAgain={() => {}} />)).toBe("");
  });
});
