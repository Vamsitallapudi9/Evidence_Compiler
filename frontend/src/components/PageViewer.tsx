import { useEffect, useRef } from "react";
import { errorMessage } from "../api/client";
import { usePageText } from "../api/hooks";
import { splitAt } from "../lib/highlight";
import { Spinner } from "./badges";

interface Props {
  sourceId: string | undefined;
  page: number;
  charStart: number;
  charEnd: number;
  /** PDFs have pages; web pages, Word and text documents have sections. */
  unit?: "page" | "section";
}

/** Canonical page (or document section) text with the evidence span [charStart, charEnd) highlighted. */
export function PageViewer({ sourceId, page, charStart, charEnd, unit = "page" }: Props) {
  const { data, isLoading, error } = usePageText(sourceId, page, true);
  const boxRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLElement>(null);

  // Scroll only the page box (not the whole drawer) so the highlighted span is centered.
  useEffect(() => {
    const box = boxRef.current;
    const mark = markRef.current;
    if (!box || !mark) return;
    box.scrollTop = Math.max(0, mark.offsetTop - box.clientHeight / 2 + mark.offsetHeight / 2);
  }, [data]);

  const what = unit === "page" ? `page ${page}` : page > 1 ? `section ${page}` : "the document";
  if (!sourceId) return <p className="text-xs text-zinc-500">No source recorded for this passage.</p>;
  if (isLoading)
    return (
      <p className="flex items-center gap-2 text-xs text-zinc-500">
        <Spinner /> Loading {what}…
      </p>
    );
  if (error || !data)
    return <p className="text-xs text-red-700">Could not load {what}: {errorMessage(error)}</p>;

  const [before, hit, after] = splitAt(data.text, [charStart, charEnd]);
  const heading =
    unit === "page"
      ? `Page ${data.page} of ${data.page_count}`
      : data.page_count > 1
        ? `Section ${data.page} of ${data.page_count}`
        : "Document text";
  return (
    <div className="rounded border border-zinc-200 bg-zinc-50">
      <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-1.5 text-xs text-zinc-500">
        <span>{heading}</span>
        <span className="font-mono">
          chars {charStart}–{charEnd}
        </span>
      </div>
      <div
        ref={boxRef}
        tabIndex={0}
        aria-label={unit === "page" ? `Text of page ${data.page}` : data.page_count > 1 ? `Text of section ${data.page}` : "Document text"}
        className="relative max-h-72 overflow-y-auto px-3 py-2 font-serif text-[13px] leading-relaxed whitespace-pre-wrap text-zinc-700">
        {before}
        <mark ref={markRef} className="rounded-sm bg-yellow-200 px-0.5 text-zinc-900">
          {hit}
        </mark>
        {after}
      </div>
    </div>
  );
}
