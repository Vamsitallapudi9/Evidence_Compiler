import { useRuns } from "../api/hooks";
import { formatDateTime } from "../lib/format";
import { RUN_STATUS_STYLES, runDisplayStatus } from "../lib/runMonitor";

interface Props {
  activeRunId: string | null;
  onSelect: (runId: string) => void;
}

export function RecentRuns({ activeRunId, onSelect }: Props) {
  const { data, isLoading, error } = useRuns();

  return (
    <section aria-labelledby="runs-heading" className="space-y-2">
      <h2 id="runs-heading" className="text-xs font-semibold tracking-wider text-zinc-500 uppercase">
        Recent runs
      </h2>
      {isLoading ? <p className="text-sm text-zinc-500">Loading…</p> : null}
      {error ? <p className="text-xs text-zinc-500">Runs unavailable.</p> : null}
      {data && !data.length ? <p className="text-sm text-zinc-500">No runs yet.</p> : null}
      {data?.length ? (
        <ul className="space-y-0.5">
          {data.map((r) => {
            const status = RUN_STATUS_STYLES[runDisplayStatus(r.status, r.error)];
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  aria-current={r.id === activeRunId ? "true" : undefined}
                  className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-zinc-100 ${
                    r.id === activeRunId ? "bg-zinc-100" : ""
                  }`}
                >
                  <span
                    className={`mt-1.5 size-2 shrink-0 rounded-full ${status?.dot ?? "bg-zinc-300"}`}
                    aria-label={status?.label ?? r.status}
                    title={status?.label ?? r.status}
                    role="img"
                  />
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm text-zinc-800">{r.question}</span>
                    <span className="text-[11px] text-zinc-400">
                      {formatDateTime(r.created_at)}
                      {status && r.status !== "done" && r.status !== "running" ? (
                        <span className={status.text}> · {status.label}</span>
                      ) : null}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
