import { useCallback, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { Answer, Claim, ClaimType } from "../api/types";
import { CLAIM_TYPE_STYLES, isProblemStatus } from "../lib/claimStyles";
import { parseAnswer } from "../lib/parseAnswer";
import type { InspectorTarget } from "../lib/selection";
import { ClaimInspector } from "./ClaimInspector";
import { ClaimList } from "./ClaimList";
import { EvidenceGraph } from "./EvidenceGraph";

export type AnswerTabId = "answer" | "graph";
type Tab = AnswerTabId;
const TABS: { id: Tab; label: string }[] = [
  { id: "answer", label: "Answer" },
  { id: "graph", label: "Evidence graph" },
];

interface AnswerViewProps {
  answer: Answer;
  initialTab?: AnswerTabId;
  initialTarget?: InspectorTarget | null;
}

export function AnswerView({ answer, initialTab = "answer", initialTarget = null }: AnswerViewProps) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [target, setTarget] = useState<InspectorTarget | null>(initialTarget);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ answer: null, graph: null });

  const close = useCallback(() => setTarget(null), []);
  const selectClaim = useCallback((id: string) => setTarget({ kind: "claim", id }), []);

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.findIndex((t) => t.id === tab);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const supportedCount = answer.claims.filter((c) => c.status === "supported").length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-zinc-200">
        <div role="tablist" aria-label="Answer views" className="-mb-px flex gap-1" onKeyDown={onTabKey}>
          {TABS.map((t) => (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[t.id] = el;
              }}
              id={`tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-3 py-2 text-sm font-medium ${
                tab === t.id ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="pb-2 text-xs text-zinc-500">
          {answer.claims.length} claims · {supportedCount} supported · {Object.keys(answer.evidence).length} evidence items
        </p>
      </div>

      <div id="panel-answer" role="tabpanel" aria-labelledby="tab-answer" hidden={tab !== "answer"}>
        <AnswerTab answer={answer} selectedId={target?.kind === "claim" ? target.id : null} onSelectClaim={selectClaim} />
      </div>
      <div id="panel-graph" role="tabpanel" aria-labelledby="tab-graph" hidden={tab !== "graph"}>
        {tab === "graph" ? (
          <>
            <GraphLegend />
            <EvidenceGraph answer={answer} onSelect={setTarget} />
          </>
        ) : null}
      </div>

      <ClaimInspector answer={answer} target={target} onClose={close} onSelect={setTarget} />
    </div>
  );
}

function AnswerTab({
  answer,
  selectedId,
  onSelectClaim,
}: {
  answer: Answer;
  selectedId: string | null;
  onSelectClaim: (id: string) => void;
}) {
  return (
    <div className="space-y-8">
      <section aria-label="Answer">
        {answer.insufficient ? (
          <div role="status" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
            <p className="font-semibold text-amber-900">Insufficient evidence available.</p>
            <p className="mt-0.5 text-sm text-amber-800">
              The sources do not contain enough evidence to answer this question reliably. See the gaps below.
            </p>
          </div>
        ) : null}
        {answer.text.trim() ? (
          <AnswerProse answer={answer} selectedId={selectedId} onSelectClaim={onSelectClaim} />
        ) : !answer.insufficient ? (
          <p className="text-sm text-zinc-500">The answer is empty.</p>
        ) : null}
        <Legend />
      </section>

      <section aria-labelledby="claims-heading">
        <h3 id="claims-heading" className="mb-3 text-sm font-semibold text-zinc-900">
          Claims
        </h3>
        <ClaimList claims={answer.claims} selectedId={selectedId} onSelect={onSelectClaim} />
      </section>

      <section aria-labelledby="gaps-heading">
        <h3 id="gaps-heading" className="mb-2 text-sm font-semibold text-zinc-900">
          Gaps
        </h3>
        {answer.gaps.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-700">
            {answer.gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-zinc-500">No evidence gaps were identified.</p>
        )}
      </section>

      {answer.warnings.length ? (
        <section aria-labelledby="warnings-heading">
          <h3 id="warnings-heading" className="mb-2 text-sm font-semibold text-zinc-900">
            Warnings
          </h3>
          <ul className="space-y-1.5">
            {answer.warnings.map((w, i) => (
              <li key={i} className="flex gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <span aria-hidden="true">⚠</span>
                {w}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function styleFor(claim: Claim): ClaimType {
  return isProblemStatus(claim.status) ? "unsupported" : claim.type;
}

function AnswerProse({
  answer,
  selectedId,
  onSelectClaim,
}: {
  answer: Answer;
  selectedId: string | null;
  onSelectClaim: (id: string) => void;
}) {
  const byId = useMemo(() => new Map(answer.claims.map((c) => [c.id, c])), [answer.claims]);
  const segments = useMemo(() => parseAnswer(answer.text, byId.keys()), [answer.text, byId]);

  const activate = (id: string) => (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelectClaim(id);
    }
  };

  return (
    <div className="max-w-3xl text-[17px] leading-8 whitespace-pre-line text-zinc-800">
      {segments.map((seg, i) => {
        if (seg.kind === "text") return <span key={i}>{seg.text}</span>;
        const claims = seg.claimIds.map((id) => byId.get(id)).filter((c): c is Claim => Boolean(c));
        const [first, ...rest] = claims;
        if (!first) return <span key={i}>{seg.text}</span>;
        const s = CLAIM_TYPE_STYLES[styleFor(first)];
        const selected = seg.claimIds.includes(selectedId ?? "");
        return (
          <span key={i}>
            <span
              role="button"
              tabIndex={0}
              aria-label={`${s.label} claim (${first.status}): ${first.text}`}
              onClick={() => onSelectClaim(first.id)}
              onKeyDown={activate(first.id)}
              className={`cursor-pointer rounded-sm underline decoration-2 underline-offset-4 transition-colors ${s.span} ${
                selected ? "bg-zinc-100" : ""
              }`}
            >
              {seg.text}
            </span>
            {[first, ...rest].map((c) => {
              const cs = CLAIM_TYPE_STYLES[styleFor(c)];
              return (
                <sup
                  key={c.id}
                  role={c === first ? undefined : "button"}
                  tabIndex={c === first ? undefined : 0}
                  aria-hidden={c === first ? true : undefined}
                  aria-label={c === first ? undefined : `${cs.label} claim: ${c.text}`}
                  onClick={() => onSelectClaim(c.id)}
                  onKeyDown={c === first ? undefined : activate(c.id)}
                  className={`ml-0.5 cursor-pointer rounded px-1 py-px text-[10px] font-semibold ring-1 ring-inset ${cs.badge}`}
                >
                  {cs.short}
                </sup>
              );
            })}
          </span>
        );
      })}
    </div>
  );
}

const LEGEND_TYPES: ClaimType[] = ["primary", "derived", "interpretation", "unsupported"];

function Legend() {
  return (
    <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 border-t border-zinc-100 pt-3 text-xs text-zinc-600" aria-label="Legend">
      {LEGEND_TYPES.map((t) => {
        const s = CLAIM_TYPE_STYLES[t];
        return (
          <span key={t} className="flex items-center gap-1.5" title={s.description}>
            <span className={`underline decoration-2 underline-offset-4 ${s.span}`}>{s.label}</span>
            <sup className={`rounded px-1 py-px text-[10px] font-semibold ring-1 ring-inset ${s.badge}`}>{s.short}</sup>
            <span className="text-zinc-500">{s.description}</span>
          </span>
        );
      })}
    </div>
  );
}

function GraphLegend() {
  const items: { label: string; bg: string; border: string; dashed?: boolean }[] = [
    { label: "Question", bg: "#18181b", border: "#18181b" },
    ...LEGEND_TYPES.map((t) => ({ label: `Claim: ${CLAIM_TYPE_STYLES[t].label}`, ...CLAIM_TYPE_STYLES[t].node, dashed: t === "unsupported" })),
    { label: "Calculation", bg: "#f5f3ff", border: "#8b5cf6" },
    { label: "Primary evidence", bg: "#eff6ff", border: "#93c5fd" },
    { label: "Derived evidence", bg: "#f0fdfa", border: "#5eead4" },
    { label: "Flagged evidence", bg: "#fef2f2", border: "#dc2626", dashed: true },
    { label: "Source", bg: "#fafafa", border: "#a1a1aa" },
  ];
  return (
    <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-zinc-600" aria-label="Graph legend">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-3 rounded-sm"
            style={{ background: it.bg, border: `1.5px ${it.dashed ? "dashed" : "solid"} ${it.border}` }}
          />
          {it.label}
        </span>
      ))}
      <span className="text-zinc-400">Click a claim, calculation or evidence node to inspect it.</span>
    </div>
  );
}
