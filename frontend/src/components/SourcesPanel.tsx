import { useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { ApiError, errorMessage } from "../api/client";
import { useAddHuggingFace, useAddPostgres, useAddUrl, useDeleteSource, useSources, useUploadSource } from "../api/hooks";
import type { SourceOut } from "../api/types";
import { formatDateTime, isDocumentKind, sourceSubtitle } from "../lib/format";
import { normalizeHfDataset } from "../lib/huggingface";
import { ExternalLink, SourceKindBadge, Spinner, WarningBadge } from "./badges";

const ACCEPT = ".pdf,.csv,.xlsx,.docx,.txt,.md";
const ACCEPTED_EXT = /\.(pdf|csv|xlsx|docx|txt|md)$/i;

export function SourcesPanel() {
  const sources = useSources();

  return (
    <section aria-labelledby="sources-heading" className="space-y-3">
      <h2 id="sources-heading" className="text-xs font-semibold tracking-wider text-zinc-500 uppercase">
        Sources
      </h2>
      <SourceList query={sources} />
      <UploadZone />
      <div className="space-y-2">
        <PostgresForm />
        <UrlForm />
        <HuggingFaceForm />
      </div>
    </section>
  );
}

function SourceList({ query }: { query: ReturnType<typeof useSources> }) {
  const del = useDeleteSource();
  const { data, isLoading, error } = query;

  if (isLoading) {
    return (
      <p className="flex items-center gap-2 text-sm text-zinc-500">
        <Spinner /> Loading sources…
      </p>
    );
  }
  if (error) {
    const down = error instanceof ApiError && error.isNetworkError;
    return (
      <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        <p className="font-medium">{down ? "Backend unreachable" : "Could not load sources"}</p>
        <p className="mt-0.5 text-xs">{down ? "Start the API server on localhost:8000, then retry." : errorMessage(error)}</p>
        <button type="button" className="btn-ghost mt-1.5" onClick={() => void query.refetch()}>
          Retry
        </button>
      </div>
    );
  }
  if (!data?.length) {
    return <p className="rounded-md border border-dashed border-zinc-300 px-3 py-4 text-center text-sm text-zinc-500">No sources yet.</p>;
  }

  const onDelete = (s: SourceOut) => {
    if (window.confirm(`Delete “${s.name}” and its ${s.evidence_count} evidence items?`)) del.mutate(s.id);
  };

  return (
    <>
      <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white">
        {data.map((s) => (
          <li key={s.id} className="group flex items-start gap-2 px-2.5 py-2">
            <SourceKindBadge kind={s.kind} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-zinc-900" title={s.name}>
                {s.name}
              </p>
              <p className="mt-0.5 text-xs text-zinc-500">{sourceSubtitle(s)}</p>
              {s.tables.length ? (
                <p className="mt-0.5 truncate font-mono text-[11px] text-zinc-500" title={s.tables.join(", ")}>
                  {s.tables.join(", ")}
                </p>
              ) : null}
              {s.url ? (
                <div className="mt-0.5 flex min-w-0">
                  <ExternalLink href={s.url} />
                </div>
              ) : null}
              {s.license || s.fetched_at ? (
                <p className="mt-0.5 truncate text-[11px] text-zinc-400">
                  {s.license ? <span title="License reported by the source">{`License: ${s.license}`}</span> : null}
                  {s.license && s.fetched_at ? " · " : null}
                  {s.fetched_at ? <span title={s.fetched_at}>{`Fetched ${formatDateTime(s.fetched_at)}`}</span> : null}
                </p>
              ) : null}
              {s.flagged_count > 0 ? (
                <div className="mt-1">
                  <WarningBadge title="Evidence items with security flags (e.g. possible prompt injection)">
                    {s.flagged_count} flagged
                  </WarningBadge>
                </div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => onDelete(s)}
              disabled={del.isPending && del.variables === s.id}
              aria-label={`Delete source ${s.name}`}
              className="rounded p-1 text-zinc-400 opacity-60 group-hover:opacity-100 hover:bg-red-50 hover:text-red-700 focus-visible:opacity-100 disabled:opacity-40"
            >
              <TrashIcon />
            </button>
          </li>
        ))}
      </ul>
      {del.error ? (
        <p role="alert" className="text-xs text-red-700">
          Delete failed: {errorMessage(del.error)}
        </p>
      ) : null}
    </>
  );
}

function UploadZone() {
  const upload = useUploadSource();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [lastName, setLastName] = useState<string | null>(null);

  const send = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setLastName(file.name);
    if (!ACCEPTED_EXT.test(file.name)) {
      setLocalError("Unsupported file type. Use .pdf, .csv or .xlsx.");
      return;
    }
    setLocalError(null);
    upload.mutate(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    send(e.dataTransfer.files);
  };

  const err = localError ?? (upload.error ? errorMessage(upload.error) : null);

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-lg border border-dashed px-3 py-3 text-center text-xs transition-colors ${
          dragging ? "border-zinc-600 bg-zinc-100" : "border-zinc-300 bg-white"
        }`}
      >
        {upload.isPending ? (
          <p className="flex items-center justify-center gap-2 text-zinc-600">
            <Spinner /> Ingesting {lastName}…
          </p>
        ) : (
          <>
            <p className="text-zinc-500">Drop a PDF, Word, text, CSV or XLSX file here</p>
            <button type="button" className="btn-ghost mt-1.5" onClick={() => inputRef.current?.click()}>
              Choose file…
            </button>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          tabIndex={-1}
          aria-label="Upload source file"
          onChange={(e) => {
            send(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {err ? (
        <p role="alert" className="mt-1.5 text-xs text-red-700">
          Upload of {lastName ?? "file"} failed: {err}
        </p>
      ) : upload.isSuccess && upload.data ? (
        <p role="status" className="mt-1.5 text-xs text-emerald-700">
          Added {upload.data.name}
          {addedSummary(upload.data)}
        </p>
      ) : null}
    </div>
  );
}

function PostgresForm() {
  const add = useAddPostgres();
  const [name, setName] = useState("");
  const [dsn, setDsn] = useState("");
  const [schema, setSchema] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !dsn.trim()) return;
    add.mutate(
      { name: name.trim(), dsn: dsn.trim(), ...(schema.trim() ? { schema: schema.trim() } : {}) },
      {
        onSuccess: () => {
          setName("");
          setDsn("");
          setSchema("");
        },
      },
    );
  };

  return (
    <Disclosure title="Add Postgres">
      <form onSubmit={submit} className={FORM}>
        <label className="block text-[11px] text-zinc-500">
          Name
          <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} placeholder="warehouse" required />
        </label>
        <label className="block text-[11px] text-zinc-500">
          DSN
          <input
            className={`${INPUT} font-mono`}
            value={dsn}
            onChange={(e) => setDsn(e.target.value)}
            placeholder="postgresql://user:pass@host:5432/db"
            autoComplete="off"
            spellCheck={false}
            required
          />
        </label>
        <label className="block text-[11px] text-zinc-500">
          Schema <span className="text-zinc-400">(optional)</span>
          <input className={INPUT} value={schema} onChange={(e) => setSchema(e.target.value)} placeholder="public" />
        </label>
        <button type="submit" className="btn-primary w-full justify-center py-1 text-xs" disabled={add.isPending || !name.trim() || !dsn.trim()}>
          {add.isPending ? "Connecting…" : "Connect"}
        </button>
        {add.error ? (
          <p role="alert" className="text-xs text-red-700">
            {errorMessage(add.error)}
          </p>
        ) : null}
      </form>
    </Disclosure>
  );
}

const INPUT =
  "block w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none";
const FORM = "space-y-2 border-t border-zinc-100 px-3 py-2.5";

function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="rounded-lg border border-zinc-200 bg-white">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-zinc-700 select-none hover:text-zinc-900">
        {title}
      </summary>
      {children}
    </details>
  );
}

/** " (12 evidence items)." for documents, " (table_a, table_b)." for tabular sources. */
function addedSummary(s: SourceOut): string {
  if (isDocumentKind(s.kind)) return ` (${s.evidence_count} evidence ${s.evidence_count === 1 ? "item" : "items"}).`;
  const passages = s.kind === "huggingface" && s.evidence_count > 0 ? `; ${s.evidence_count} passages` : "";
  return s.tables.length ? ` (${s.tables.join(", ")}${passages}).` : ".";
}

function UrlForm() {
  const add = useAddUrl();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const trimmed = url.trim();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!trimmed || add.isPending) return;
    add.mutate(
      { url: trimmed, ...(name.trim() ? { name: name.trim() } : {}) },
      {
        onSuccess: () => {
          setUrl("");
          setName("");
        },
      },
    );
  };

  return (
    <Disclosure title="Add from link">
      <form onSubmit={submit} className={FORM}>
        <label className="block text-[11px] text-zinc-500">
          URL
          <input
            type="url"
            className={INPUT}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://… (PDF, Word, Google Doc, web page, CSV)"
            autoComplete="off"
            spellCheck={false}
            required
            disabled={add.isPending}
          />
        </label>
        <label className="block text-[11px] text-zinc-500">
          Name <span className="text-zinc-400">(optional)</span>
          <input
            className={INPUT}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Defaults to the page title or file name"
            disabled={add.isPending}
          />
        </label>
        <button type="submit" className="btn-primary w-full justify-center py-1 text-xs" disabled={add.isPending || !trimmed}>
          {add.isPending ? (
            <>
              <Spinner className="border-zinc-500 border-t-white" /> Fetching…
            </>
          ) : (
            "Add"
          )}
        </button>
        <MutationStatus mutation={add} pendingNote="Fetching and extracting; this can take up to 30 seconds." />
      </form>
    </Disclosure>
  );
}

const HF_MAX_ROWS = 20_000;
const HF_DEFAULT_ROWS = 2_000;

function HuggingFaceForm() {
  const add = useAddHuggingFace();
  const [dataset, setDataset] = useState("");
  const [config, setConfig] = useState("");
  const [split, setSplit] = useState("");
  const [maxRows, setMaxRows] = useState(String(HF_DEFAULT_ROWS));
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (add.isPending) return;
    const name = normalizeHfDataset(dataset);
    if (!name) {
      setLocalError("Enter a dataset as owner/name or paste its huggingface.co/datasets/… URL.");
      return;
    }
    const rows = Number(maxRows);
    if (!Number.isInteger(rows) || rows < 1 || rows > HF_MAX_ROWS) {
      setLocalError(`Max rows must be a whole number between 1 and ${HF_MAX_ROWS.toLocaleString("en-US")}.`);
      return;
    }
    setLocalError(null);
    setDataset(name);
    add.mutate(
      {
        dataset: name,
        ...(config.trim() ? { config: config.trim() } : {}),
        ...(split.trim() ? { split: split.trim() } : {}),
        max_rows: rows,
      },
      {
        onSuccess: () => {
          setDataset("");
          setConfig("");
          setSplit("");
        },
      },
    );
  };

  return (
    <Disclosure title="Add Hugging Face dataset">
      <form onSubmit={submit} className={FORM} noValidate>
        <label className="block text-[11px] text-zinc-500">
          Dataset
          <input
            className={`${INPUT} font-mono`}
            value={dataset}
            onChange={(e) => {
              setDataset(e.target.value);
              setLocalError(null);
            }}
            onBlur={() => {
              // Turn a pasted hub URL into owner/name as soon as the field loses focus.
              const name = normalizeHfDataset(dataset);
              if (name && name !== dataset) setDataset(name);
            }}
            placeholder="owner/dataset, e.g. stanfordnlp/imdb"
            autoComplete="off"
            spellCheck={false}
            required
            disabled={add.isPending}
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-[11px] text-zinc-500">
            Config <span className="text-zinc-400">(optional)</span>
            <input className={INPUT} value={config} onChange={(e) => setConfig(e.target.value)} placeholder="default" disabled={add.isPending} />
          </label>
          <label className="block text-[11px] text-zinc-500">
            Split <span className="text-zinc-400">(optional)</span>
            <input className={INPUT} value={split} onChange={(e) => setSplit(e.target.value)} placeholder="train" disabled={add.isPending} />
          </label>
        </div>
        <label className="block text-[11px] text-zinc-500">
          Max rows
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={HF_MAX_ROWS}
            step={1}
            className={INPUT}
            value={maxRows}
            onChange={(e) => {
              setMaxRows(e.target.value);
              setLocalError(null);
            }}
            disabled={add.isPending}
          />
        </label>
        <p className="text-[11px] leading-snug text-zinc-400">Tables are queried with SQL; long text columns become searchable passages.</p>
        <button type="submit" className="btn-primary w-full justify-center py-1 text-xs" disabled={add.isPending || !dataset.trim()}>
          {add.isPending ? (
            <>
              <Spinner className="border-zinc-500 border-t-white" /> Downloading from Hugging Face…
            </>
          ) : (
            "Add"
          )}
        </button>
        {localError ? (
          <p role="alert" className="text-xs text-red-700">
            {localError}
          </p>
        ) : (
          <MutationStatus mutation={add} pendingNote="Large datasets can take up to a minute." />
        )}
      </form>
    </Disclosure>
  );
}

/** Pending note, success confirmation or backend error (`detail`) for an add-source mutation. */
function MutationStatus({
  mutation,
  pendingNote,
}: {
  mutation: { isPending: boolean; isSuccess: boolean; error: unknown; data?: SourceOut };
  pendingNote: ReactNode;
}) {
  if (mutation.isPending) {
    return (
      <p role="status" className="text-[11px] text-zinc-500">
        {pendingNote}
      </p>
    );
  }
  if (mutation.error) {
    return (
      <p role="alert" className="text-xs text-red-700">
        {errorMessage(mutation.error)}
      </p>
    );
  }
  if (mutation.isSuccess && mutation.data) {
    return (
      <p role="status" className="text-xs text-emerald-700">
        Added {mutation.data.name}
        {addedSummary(mutation.data)}
      </p>
    );
  }
  return null;
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-4">
      <path
        fillRule="evenodd"
        d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
