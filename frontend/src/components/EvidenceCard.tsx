import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { errorMessage } from "../api/client";
import { queryKeys, useEvidence } from "../api/hooks";
import type { Answer, Calculation, EvidenceItem, SourceOut } from "../api/types";
import { formatDateTime, formatFieldValue, formatLocation, formatValue, humanize, opLabel } from "../lib/format";
import { findHighlight, splitAt } from "../lib/highlight";
import { sourceName, upstreamIds } from "../lib/selection";
import { OriginBadge, Spinner } from "./badges";
import { PageViewer } from "./PageViewer";

const MAX_DEPTH = 5;

interface EvidenceCardProps {
  evidenceId: string;
  answer: Answer | undefined;
  relation?: string;
  quote?: string | null;
  quoteSpan?: [number, number] | null;
  /** Evidence IDs above this card in the drill-down chain (cycle guard). */
  ancestors?: string[];
}

/** One evidence item: origin, source, location, text with quote highlight, fields, flags, drill-down. */
export function EvidenceCard({ evidenceId, answer, relation, quote, quoteSpan, ancestors = [] }: EvidenceCardProps) {
  const embedded = answer?.evidence[evidenceId];
  const { data: item, isLoading, error } = useEvidence(evidenceId, embedded);

  if (!item) {
    return (
      <article className="rounded-lg border border-zinc-200 bg-white p-3 text-sm">
        <p className="font-mono text-xs text-zinc-500">{evidenceId}</p>
        {isLoading ? (
          <p className="mt-1 flex items-center gap-2 text-zinc-500">
            <Spinner /> Loading evidence…
          </p>
        ) : (
          <p className="mt-1 text-red-700">Evidence unavailable: {errorMessage(error ?? "not found")}</p>
        )}
      </article>
    );
  }

  return (
    <EvidenceBody item={item} answer={answer} relation={relation} quote={quote} quoteSpan={quoteSpan} ancestors={ancestors} />
  );
}

function EvidenceBody({
  item,
  answer,
  relation,
  quote,
  quoteSpan,
  ancestors,
}: Omit<EvidenceCardProps, "evidenceId" | "ancestors"> & { item: EvidenceItem; ancestors: string[] }) {
  const [showPage, setShowPage] = useState(false);
  const [showUpstream, setShowUpstream] = useState(false);
  const upstreamRegion = useId();
  const pageRegion = useId();

  const loc = item.location;
  const highlight = findHighlight(item.text, quote, quoteSpan);
  const [before, hit, after] = highlight ? splitAt(item.text, highlight) : [item.text, "", ""];
  const fields = Object.entries(item.fields);
  const upstream = upstreamIds(item, answer).filter((id) => !ancestors.includes(id));
  const calc = item.calculation_id ? answer?.calculations[item.calculation_id] : undefined;
  const canDrill = upstream.length > 0 && ancestors.length < MAX_DEPTH;
  const flagged = item.security_flags.length > 0;
  const pageCount = useSourcePageCount(item.source_ids[0], answer);
  // PDF pages and document sections (web pages, Word, text) can be opened in the page viewer.
  const viewable = loc.kind === "pdf" || loc.kind === "text" ? loc : null;
  const viewLabel = loc.kind === "pdf" ? `View page ${loc.page}` : "View in document";

  return (
    <article
      className={`rounded-lg border bg-white p-3 text-sm ${flagged ? "border-red-300" : "border-zinc-200"}`}
      aria-label={`Evidence ${item.id}`}
    >
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <OriginBadge origin={item.origin} creator={item.creator} />
          {relation ? (
            <span className={`text-xs ${relation === "contradicts" ? "font-semibold text-red-700" : "text-zinc-500"}`}>
              {humanize(relation)}
            </span>
          ) : null}
          <span className="min-w-0 truncate font-medium text-zinc-800">
            {item.source_ids.length ? item.source_ids.map((s) => sourceName(s, answer)).join(", ") : "—"}
          </span>
        </div>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-xs">
          <span className="text-zinc-600">{formatLocation(loc, { pageCount })}</span>
          <span className="font-mono text-[10px] text-zinc-400" title="Evidence ID">
            {item.id}
          </span>
        </div>
      </header>

      {flagged ? (
        <div role="alert" className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-800">
          <p className="font-semibold">⚠ Security flag{item.security_flags.length > 1 ? "s" : ""}</p>
          <ul className="mt-0.5 list-disc pl-4">
            {item.security_flags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {loc.kind === "query" ? (
        <div className="mt-2">
          <pre className="overflow-x-auto rounded bg-zinc-900 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-100">
            <code>{loc.sql}</code>
          </pre>
          <p className="mt-1 text-xs text-zinc-500">
            {loc.engine} · tables: {loc.tables.join(", ") || "—"} · executed {formatDateTime(loc.executed_at)}
          </p>
        </div>
      ) : null}

      <blockquote className="mt-2 border-l-2 border-zinc-300 pl-3 leading-relaxed whitespace-pre-wrap text-zinc-700">
        {before}
        {hit ? <mark className="rounded-sm bg-yellow-200 px-0.5 text-zinc-900">{hit}</mark> : null}
        {after}
      </blockquote>
      {quote && !highlight ? (
        <p className="mt-1 text-xs text-amber-700">Quoted text “{quote}” was not found verbatim in this evidence.</p>
      ) : null}

      {fields.length ? (
        <table className="mt-2 w-full text-xs">
          <caption className="sr-only">Structured fields</caption>
          <tbody>
            {fields.map(([k, v]) => (
              <tr key={k} className="border-t border-zinc-100 first:border-t-0">
                <th scope="row" className="w-2/5 py-1 pr-2 text-left font-mono font-normal text-zinc-500">
                  {k}
                </th>
                <td className="py-1 font-mono text-zinc-800">{formatFieldValue(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {(viewable || canDrill) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {viewable ? (
            <button
              type="button"
              className="btn-ghost"
              aria-expanded={showPage}
              aria-controls={pageRegion}
              onClick={() => setShowPage((v) => !v)}
            >
              {showPage ? (viewable.kind === "pdf" ? "Hide page" : "Hide document") : viewLabel}
            </button>
          ) : null}
          {canDrill ? (
            <button
              type="button"
              className="btn-ghost"
              aria-expanded={showUpstream}
              aria-controls={upstreamRegion}
              onClick={() => setShowUpstream((v) => !v)}
            >
              {showUpstream ? "Hide" : "Show"} upstream evidence ({upstream.length})
            </button>
          ) : null}
        </div>
      )}

      {viewable && showPage ? (
        <div id={pageRegion} className="mt-2">
          <PageViewer
            sourceId={item.source_ids[0]}
            page={viewable.page}
            charStart={viewable.char_start}
            charEnd={viewable.char_end}
            unit={viewable.kind === "pdf" ? "page" : "section"}
          />
        </div>
      ) : null}

      {canDrill && showUpstream ? (
        <div id={upstreamRegion} className="mt-3 space-y-2 border-l-2 border-teal-200 pl-3">
          {calc ? <CalculationView calc={calc} answer={answer} ancestors={[...ancestors, item.id]} nested /> : null}
          {(calc ? item.derived_from.filter((id) => !ancestors.includes(id)) : upstream).map((id) => (
            <EvidenceCard key={id} evidenceId={id} answer={answer} relation="derived_from" ancestors={[...ancestors, item.id]} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

/**
 * Page/section count of a source: from the answer's embedded source metadata, otherwise from
 * the (already cached) sources list. Undefined when unknown.
 */
function useSourcePageCount(sourceId: string | undefined, answer: Answer | undefined): number | undefined {
  const qc = useQueryClient();
  if (!sourceId) return undefined;
  const fromAnswer = answer?.sources[sourceId]?.metadata.page_count;
  if (typeof fromAnswer === "number") return fromAnswer;
  const listed = qc.getQueryData<SourceOut[]>(queryKeys.sources)?.find((s) => s.id === sourceId);
  return listed?.page_count ?? undefined;
}

interface CalculationViewProps {
  calc: Calculation;
  answer: Answer | undefined;
  ancestors?: string[];
  /** Nested inside a drill-down: inputs are shown as cards directly. */
  nested?: boolean;
}

/** Deterministic calculation: op, formula, result, and each input with its evidence. */
export function CalculationView({ calc, answer, ancestors = [], nested = false }: CalculationViewProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/40 p-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-xs font-semibold text-violet-800">{calc.op}</span>
        <span className="text-xs text-zinc-500">{opLabel(calc.op)}</span>
        <span className="ml-auto text-base font-semibold text-zinc-900">= {formatValue(calc.result, calc.unit)}</span>
      </div>
      <p className="mt-1 font-mono text-xs break-words text-zinc-700">{calc.formula}</p>
      <ul className="mt-2 space-y-2">
        {calc.inputs.map((input, i) => {
          const key = `${input.name}-${i}`;
          const expanded = nested || open[key];
          const inputRegion = `${calc.id}-input-${i}`;
          return (
            <li key={key}>
              <div className="flex flex-wrap items-center gap-x-2 text-xs">
                <span className="font-mono text-zinc-500">{input.name}</span>
                <span className="font-semibold text-zinc-900">{formatValue(input.value, input.unit)}</span>
                {input.field ? <span className="font-mono text-zinc-400">({input.field})</span> : null}
                {!nested ? (
                  <button
                    type="button"
                    className="btn-ghost ml-auto"
                    aria-expanded={Boolean(expanded)}
                    aria-controls={inputRegion}
                    onClick={() => setOpen((o) => ({ ...o, [key]: !o[key] }))}
                  >
                    {expanded ? "Hide evidence" : "Show evidence"}
                  </button>
                ) : null}
              </div>
              {expanded && !ancestors.includes(input.evidence_id) ? (
                <div id={inputRegion} className="mt-1.5">
                  <EvidenceCard
                    evidenceId={input.evidence_id}
                    answer={answer}
                    relation="calculated_from"
                    quote={input.quote}
                    ancestors={ancestors}
                  />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
