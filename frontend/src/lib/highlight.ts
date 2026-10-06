export type Span = [start: number, end: number];

function validSpan(text: string, span: readonly [number, number] | null | undefined): span is Span {
  if (!span) return false;
  const [s, e] = span;
  return Number.isInteger(s) && Number.isInteger(e) && s >= 0 && e > s && e <= text.length;
}

/**
 * Locates the part of `text` to highlight for an evidence link.
 * Prefers an explicit span (if it is in range and consistent with the quote),
 * then an exact quote match, then a case-insensitive match.
 */
export function findHighlight(
  text: string,
  quote?: string | null,
  span?: readonly [number, number] | null,
): Span | null {
  const q = quote?.trim();
  if (validSpan(text, span)) {
    if (!q || text.slice(span[0], span[1]).trim().toLowerCase() === q.toLowerCase()) {
      return [span[0], span[1]];
    }
  }
  if (!q) return null;
  let idx = text.indexOf(q);
  if (idx === -1) idx = text.toLowerCase().indexOf(q.toLowerCase());
  return idx === -1 ? null : [idx, idx + q.length];
}

/** Splits text into [before, highlighted, after] around a span (clamped to bounds). */
export function splitAt(text: string, span: Span): [string, string, string] {
  const s = Math.max(0, Math.min(span[0], text.length));
  const e = Math.max(s, Math.min(span[1], text.length));
  return [text.slice(0, s), text.slice(s, e), text.slice(e)];
}
