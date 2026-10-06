import type { Answer, EvidenceItem } from "../api/types";
import { isHttpUrl } from "./format";

/** What the right-hand inspector drawer is showing. */
export type InspectorTarget = { kind: "claim"; id: string } | { kind: "evidence"; id: string };

/** Direct upstream evidence IDs: `derived_from` plus calculation inputs. */
export function upstreamIds(item: EvidenceItem, answer: Answer | undefined): string[] {
  const ids = [...item.derived_from];
  const calc = item.calculation_id ? answer?.calculations[item.calculation_id] : undefined;
  if (calc) for (const input of calc.inputs) ids.push(input.evidence_id);
  return [...new Set(ids)].filter((id) => id !== item.id);
}

/**
 * Source IDs behind a set of evidence items, walking upstream through derived
 * evidence that lacks its own source_ids.
 */
export function sourcesFor(evidenceIds: string[], answer: Answer): string[] {
  const out = new Set<string>();
  const seen = new Set<string>();
  const stack = [...evidenceIds];
  while (stack.length) {
    const id = stack.pop() as string;
    if (seen.has(id)) continue;
    seen.add(id);
    const item = answer.evidence[id];
    if (!item) continue;
    if (item.source_ids.length) item.source_ids.forEach((s) => out.add(s));
    else stack.push(...upstreamIds(item, answer));
  }
  return [...out];
}

export function sourceName(id: string, answer: Answer | undefined): string {
  return answer?.sources[id]?.name ?? id;
}

/** Original web link of a source (fetched pages/files, Hugging Face datasets), if any. */
export function sourceUrl(id: string, answer: Answer | undefined): string | null {
  const src = answer?.sources[id];
  if (!src) return null;
  const fromMeta = src.metadata.url;
  if (typeof fromMeta === "string" && isHttpUrl(fromMeta)) return fromMeta;
  return isHttpUrl(src.uri) ? src.uri : null;
}
