import type { RunEvent } from "../api/types";
import { formatTime, humanize } from "../lib/format";
import { Spinner } from "./badges";

/** Display labels for stages whose name doesn't humanize well. */
const STAGE_LABELS: Record<string, string> = {
  fetch: "Fetching links",
  sql: "SQL",
};

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? humanize(stage);
}

/** A fetch event that reports a failure ("Failed to fetch …", "Could not fetch …", or `data.error` / `data.ok: false`). */
function isFailedFetch(e: RunEvent): boolean {
  if (e.stage !== "fetch") return false;
  if (e.data?.error || e.data?.ok === false) return true;
  return /^\s*(failed|fetch failed|could ?n[o']t|cannot|unable|error|blocked|skipp(ed|ing))\b/i.test(e.message);
}

interface Props {
  events: RunEvent[];
  running: boolean;
}

export function ProgressTimeline({ events, running }: Props) {
  return (
    <section aria-label="Run progress" className="rounded-lg border border-zinc-200 bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-800">
        {running ? <Spinner /> : null}
        {running ? "Compiling evidence…" : "Progress"}
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-zinc-500">{running ? "Waiting for the first update…" : "No progress events recorded."}</p>
      ) : (
        <ol className="relative space-y-2 border-l border-zinc-200 pl-4" aria-live="polite">
          {events.map((e, i) => {
            const last = i === events.length - 1;
            const isFetch = e.stage === "fetch";
            const failed = isFailedFetch(e);
            return (
              <li key={`${e.ts}-${i}`} className="relative">
                <span
                  aria-hidden="true"
                  className={`absolute top-1.5 -left-[21px] size-2.5 rounded-full ring-2 ring-white ${
                    last && running ? "animate-pulse bg-zinc-800" : failed ? "bg-amber-500" : isFetch ? "bg-sky-500" : "bg-zinc-400"
                  }`}
                />
                <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className={`inline-flex items-center gap-1 self-center font-medium ${isFetch ? "text-sky-800" : "text-zinc-800"}`}>
                    {isFetch ? <LinkIcon /> : null}
                    {stageLabel(e.stage)}
                  </span>
                  <span className={`min-w-0 break-words ${failed ? "text-amber-800" : "text-zinc-600"}`}>{e.message}</span>
                  <time className="ml-auto font-mono text-xs text-zinc-400" dateTime={e.ts}>
                    {formatTime(e.ts)}
                  </time>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function LinkIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="size-3.5">
      <path d="M8.914 6.025a.75.75 0 0 1 1.06 0 3.5 3.5 0 0 1 0 4.95l-2 2a3.5 3.5 0 0 1-5.396-4.402.75.75 0 0 1 1.251.827 2 2 0 0 0 3.085 2.514l2-2a2 2 0 0 0 0-2.828.75.75 0 0 1 0-1.06Z" />
      <path d="M7.086 9.975a.75.75 0 0 1-1.06 0 3.5 3.5 0 0 1 0-4.95l2-2a3.5 3.5 0 0 1 5.396 4.402.75.75 0 0 1-1.251-.827 2 2 0 0 0-3.085-2.514l-2 2a2 2 0 0 0 0 2.828.75.75 0 0 1 0 1.06Z" />
    </svg>
  );
}
