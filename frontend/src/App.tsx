import { useCallback, useState } from "react";
import { useRecoverOnReconnect, useSources } from "./api/hooks";
import { AskView } from "./components/AskView";
import { Layout } from "./components/Layout";
import { RecentRuns } from "./components/RecentRuns";
import { SourcesPanel } from "./components/SourcesPanel";

function readRunParam(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

/** Keeps the active run in the URL (?run=<id>) so reloads and links restore it. */
function useActiveRun(): [string | null, (id: string) => void] {
  const [runId, setRunId] = useState<string | null>(readRunParam);
  const select = useCallback((id: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("run", id);
    window.history.replaceState(null, "", url);
    setRunId(id);
  }, []);
  return [runId, select];
}

export default function App() {
  const [runId, setRunId] = useActiveRun();
  useRecoverOnReconnect();
  const sources = useSources();
  const hasSources = (sources.data?.length ?? 0) > 0;

  return (
    <Layout
      sidebar={
        <>
          <SourcesPanel />
          <RecentRuns activeRunId={runId} onSelect={setRunId} />
        </>
      }
    >
      <AskView runId={runId} onRunCreated={setRunId} hasSources={hasSources || sources.isLoading || sources.isError} />
    </Layout>
  );
}
