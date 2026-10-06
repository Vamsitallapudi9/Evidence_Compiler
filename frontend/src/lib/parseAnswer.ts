/**
 * Parses answer prose containing inline claim markers like `[c:clm_ab12]`.
 *
 * Each marker attaches to the text immediately before it, back to the previous
 * marker or the start of the current sentence, whichever is closer. Markers are
 * never rendered. Unknown claim IDs are dropped and their text stays plain.
 */

export type AnswerSegment =
  | { kind: "text"; text: string }
  | { kind: "claim"; text: string; claimIds: string[] };

// `[c:id]`, tolerating whitespace and comma-separated ids: `[c: a, b]`.
const MARKER_RE = /\s*\[c:\s*([^\]]+?)\s*\]/g;

// Last sentence boundary: terminal punctuation (optionally followed by a closing
// quote/bracket) then whitespace, or a newline.
const SENTENCE_BOUNDARY_RE = /(?:[.!?]["')\]]*\s+|\n+)/g;

const LEADING_PUNCT_RE = /^[\s,;:.!?)\]]+/;

/** Index where the final sentence of `text` begins. */
function lastSentenceStart(text: string): number {
  let start = 0;
  for (const m of text.matchAll(SENTENCE_BOUNDARY_RE)) {
    const end = (m.index ?? 0) + m[0].length;
    // Ignore a boundary at the very end; it ends the span rather than starting one.
    if (end < text.length) start = end;
  }
  return start;
}

function pushText(out: AnswerSegment[], text: string): void {
  if (!text) return;
  const last = out[out.length - 1];
  if (last && last.kind === "text") last.text += text;
  else out.push({ kind: "text", text });
}

export function parseAnswer(text: string, knownClaimIds: Iterable<string>): AnswerSegment[] {
  const known = new Set(knownClaimIds);
  const out: AnswerSegment[] = [];
  let cursor = 0;

  for (const m of text.matchAll(MARKER_RE)) {
    const markerStart = m.index ?? 0;
    const ids = m[1]
      .split(",")
      .map((s) => s.trim())
      .filter((id) => id && known.has(id));
    const preceding = text.slice(cursor, markerStart);
    cursor = markerStart + m[0].length;

    if (ids.length === 0) {
      pushText(out, preceding);
      continue;
    }

    const last = out[out.length - 1];
    if (!preceding.trim() && last && last.kind === "claim") {
      // Adjacent markers (`... [c:a][c:b]`) annotate the same span.
      for (const id of ids) if (!last.claimIds.includes(id)) last.claimIds.push(id);
      pushText(out, preceding);
      continue;
    }

    const start = lastSentenceStart(preceding);
    const lead = preceding.slice(0, start);
    const body = preceding.slice(start);
    // Keep leading whitespace and dangling punctuation (", ") outside the span.
    const trimmed = body.replace(LEADING_PUNCT_RE, "");
    pushText(out, lead + body.slice(0, body.length - trimmed.length));
    if (trimmed) out.push({ kind: "claim", text: trimmed, claimIds: ids });
  }

  pushText(out, text.slice(cursor));
  return out;
}

/** Removes all claim markers, e.g. for plain-text copy. */
export function stripMarkers(text: string): string {
  return text.replace(MARKER_RE, "");
}
