import { useEffect, useRef, type ReactNode } from "react";
import type { Answer, Claim } from "../api/types";
import { CLAIM_TYPE_STYLES } from "../lib/claimStyles";
import { humanize } from "../lib/format";
import { sourceName, sourcesFor, sourceUrl, type InspectorTarget } from "../lib/selection";
import { ClaimTypeBadge, ExternalLink, StatusBadge } from "./badges";
import { CalculationView, EvidenceCard } from "./EvidenceCard";

interface Props {
  answer: Answer;
  target: InspectorTarget | null;
  onClose: () => void;
  onSelect: (target: InspectorTarget) => void;
}

/** Right-hand slide-over showing a claim's full evidence structure (or a single evidence item). */
export function ClaimInspector({ answer, target, onClose, onSelect }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const open = target !== null;

  // Esc closes; focus moves into the drawer when it opens and back when it closes.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused && document.contains(previouslyFocused)) previouslyFocused.focus();
    };
  }, [open, onClose]);

  // Reset scroll when switching between claims.
  useEffect(() => {
    panelRef.current?.scrollTo({ top: 0 });
  }, [target?.kind, target?.id]);

  const claim = target?.kind === "claim" ? answer.claims.find((c) => c.id === target.id) : undefined;
  const title = target?.kind === "evidence" ? "Evidence" : "Claim inspector";

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-labelledby="inspector-title"
      aria-hidden={!open}
      inert={!open}
      className={`fixed inset-y-0 right-0 z-40 flex w-full max-w-xl flex-col border-l border-zinc-200 bg-white shadow-2xl transition-transform duration-200 ease-out ${
        open ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3">
        <h2 id="inspector-title" className="text-sm font-semibold tracking-wide text-zinc-500 uppercase">
          {title}
        </h2>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
          aria-label="Close inspector (Esc)"
        >
          <span aria-hidden="true" className="text-lg leading-none">
            ×
          </span>
        </button>
      </div>
      <div ref={panelRef} className="flex-1 overflow-y-auto px-5 py-4">
        {target?.kind === "claim" ? (
          claim ? (
            <ClaimDetail claim={claim} answer={answer} />
          ) : (
            <p className="text-sm text-zinc-500">Claim {target.id} is not part of this answer.</p>
          )
        ) : null}
        {target?.kind === "evidence" ? (
          <EvidenceDetail evidenceId={target.id} answer={answer} onSelect={onSelect} />
        ) : null}
      </div>
    </aside>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-2.5">
      <dt className="pt-0.5 text-[11px] font-semibold tracking-wider text-zinc-500 uppercase">{label}</dt>
      <dd className="min-w-0 text-sm text-zinc-800">{children}</dd>
    </div>
  );
}

function ClaimDetail({ claim, answer }: { claim: Claim; answer: Answer }) {
  const linkedIds = claim.links.map((l) => l.evidence_id);
  const sourceIds = sourcesFor(linkedIds, answer);
  const calcId =
    claim.calculation_id ??
    linkedIds.map((id) => answer.evidence[id]?.calculation_id).find((c): c is string => Boolean(c));
  const calc = calcId ? answer.calculations[calcId] : undefined;
  const allPrimary = claim.links.length > 0 && claim.links.every((l) => answer.evidence[l.evidence_id]?.origin === "primary");

  return (
    <dl className="divide-y divide-zinc-100">
      <Row label="Claim">
        <p className="text-base leading-snug font-medium text-zinc-900">{claim.text}</p>
        {claim.origin === "hypothesis" ? (
          <p className="mt-1 text-xs text-zinc-500">Hypothesis considered during compilation (not asserted in the answer).</p>
        ) : null}
      </Row>
      <Row label="Status">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <StatusBadge status={claim.status} />
          <span className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-wider text-zinc-500 uppercase">Type</span>
            <ClaimTypeBadge type={claim.type} />
          </span>
        </div>
        <p className="mt-1.5 text-xs text-zinc-500">{CLAIM_TYPE_STYLES[claim.type].description}</p>
        {claim.reason ? <p className="mt-1.5 text-sm text-zinc-700">{claim.reason}</p> : null}
      </Row>
      <Row label="Source">
        {sourceIds.length ? (
          <ul className="space-y-0.5">
            {sourceIds.map((s) => {
              const url = sourceUrl(s, answer);
              return (
                <li key={s} className="min-w-0">
                  <span className="font-medium">{sourceName(s, answer)}</span>
                  {url ? <ExternalLink href={url} className="ml-2 align-baseline" /> : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <span className="text-zinc-500">No source</span>
        )}
      </Row>
      {calc ? (
        <Row label="Calculation">
          <CalculationView calc={calc} answer={answer} />
        </Row>
      ) : calcId ? (
        <Row label="Calculation">
          <span className="font-mono text-xs text-zinc-500">{calcId} (not included in answer)</span>
        </Row>
      ) : null}
      <Row label={allPrimary ? "Primary evidence" : "Evidence"}>
        {claim.links.length ? (
          <ul className="space-y-3">
            {claim.links.map((l, i) => (
              <li key={`${l.evidence_id}-${i}`}>
                <EvidenceCard
                  evidenceId={l.evidence_id}
                  answer={answer}
                  relation={l.relation}
                  quote={l.quote}
                  quoteSpan={l.quote_span}
                />
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded border border-dashed border-rose-300 bg-rose-50/50 px-3 py-2 text-rose-800">
            No evidence links. This claim is not backed by any source.
          </p>
        )}
      </Row>
      <Row label="Checks">
        {claim.checks.length ? (
          <ul className="space-y-1.5">
            {claim.checks.map((c, i) => (
              <li key={`${c.name}-${i}`} className="flex gap-2">
                <span
                  aria-label={c.passed ? "passed" : "failed"}
                  className={`mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${
                    c.passed ? "bg-emerald-600" : "bg-red-600"
                  }`}
                >
                  {c.passed ? "✓" : "✕"}
                </span>
                <span>
                  <span className="font-medium">{humanize(c.name)}</span>
                  {c.detail ? <span className="text-zinc-600"> — {c.detail}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-zinc-500">No checks recorded.</span>
        )}
      </Row>
      <Row label="Verifier">
        <p className="mb-1 text-[11px] font-medium text-zinc-500">Model verifier note (not evidence)</p>
        {claim.entailment ? (
          <p>
            <span
              className={`font-medium ${
                claim.entailment === "supports"
                  ? "text-emerald-700"
                  : claim.entailment === "partial"
                    ? "text-yellow-800"
                    : "text-red-700"
              }`}
            >
              {humanize(claim.entailment)}
            </span>
            {claim.entailment_note ? <span className="text-zinc-600"> — {claim.entailment_note}</span> : null}
          </p>
        ) : (
          <p className="text-zinc-500">{claim.entailment_note || "Not verified by the model."}</p>
        )}
      </Row>
    </dl>
  );
}

function EvidenceDetail({
  evidenceId,
  answer,
  onSelect,
}: {
  evidenceId: string;
  answer: Answer;
  onSelect: (t: InspectorTarget) => void;
}) {
  const referencing = answer.claims.filter((c) => c.links.some((l) => l.evidence_id === evidenceId));
  return (
    <div className="space-y-4">
      <EvidenceCard evidenceId={evidenceId} answer={answer} />
      <section>
        <h3 className="mb-1.5 text-[11px] font-semibold tracking-wider text-zinc-500 uppercase">Referenced by claims</h3>
        {referencing.length ? (
          <ul className="space-y-1">
            {referencing.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect({ kind: "claim", id: c.id })}
                  className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-zinc-50"
                >
                  <ClaimTypeBadge type={c.type} compact />
                  <span className="text-zinc-800">{c.text}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-zinc-500">No claim links this item directly (it may be upstream of one).</p>
        )}
      </section>
    </div>
  );
}
