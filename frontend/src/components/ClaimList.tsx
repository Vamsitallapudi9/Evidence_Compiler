import type { ReactNode } from "react";
import type { Claim } from "../api/types";
import { ClaimTypeBadge, StatusBadge } from "./badges";

interface Props {
  claims: Claim[];
  selectedId: string | null;
  onSelect: (claimId: string) => void;
}

export function ClaimList({ claims, selectedId, onSelect }: Props) {
  const supported = claims.filter((c) => c.status === "supported");
  const partial = claims.filter((c) => c.status === "partial");
  const problems = claims.filter((c) => c.status === "unsupported" || c.status === "rejected");

  return (
    <div className="space-y-5">
      <Group title="Supported" count={supported.length} empty="No fully supported claims.">
        {supported.map((c) => (
          <ClaimRow key={c.id} claim={c} selected={c.id === selectedId} onSelect={onSelect} />
        ))}
      </Group>
      {partial.length ? (
        <Group title="Partial" count={partial.length} empty="">
          {partial.map((c) => (
            <ClaimRow key={c.id} claim={c} selected={c.id === selectedId} onSelect={onSelect} showStatus />
          ))}
        </Group>
      ) : null}
      <Group
        title="Unsupported & rejected"
        count={problems.length}
        empty="None. Every claim considered was backed by evidence."
        tone="problem"
      >
        {problems.map((c) => (
          <ClaimRow key={c.id} claim={c} selected={c.id === selectedId} onSelect={onSelect} showStatus showReason />
        ))}
      </Group>
    </div>
  );
}

function Group({
  title,
  count,
  empty,
  tone = "default",
  children,
}: {
  title: string;
  count: number;
  empty: string;
  tone?: "default" | "problem";
  children: ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h4
        className={`mb-1.5 flex items-center gap-2 text-xs font-semibold tracking-wider uppercase ${
          tone === "problem" ? "text-rose-700" : "text-zinc-500"
        }`}
      >
        {title}
        <span className="rounded-full bg-zinc-100 px-1.5 text-[10px] text-zinc-600">{count}</span>
      </h4>
      {count ? (
        <ul className={`divide-y rounded-lg border ${tone === "problem" ? "divide-rose-100 border-rose-200" : "divide-zinc-100 border-zinc-200"}`}>
          {children}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500">{empty}</p>
      )}
    </section>
  );
}

function ClaimRow({
  claim,
  selected,
  onSelect,
  showStatus = false,
  showReason = false,
}: {
  claim: Claim;
  selected: boolean;
  onSelect: (id: string) => void;
  showStatus?: boolean;
  showReason?: boolean;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(claim.id)}
        aria-current={selected ? "true" : undefined}
        className={`flex w-full items-start gap-3 px-3 py-2.5 text-left first:rounded-t-lg last:rounded-b-lg hover:bg-zinc-50 ${
          selected ? "bg-zinc-50" : ""
        }`}
      >
        <span className="flex shrink-0 flex-col items-start gap-1 pt-0.5">
          {claim.type !== "unsupported" || !showStatus ? <ClaimTypeBadge type={claim.type} /> : null}
          {showStatus ? <StatusBadge status={claim.status} /> : null}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-zinc-900">{claim.text}</span>
          {claim.origin === "hypothesis" ? (
            <span className="mt-0.5 block text-xs text-zinc-500 italic">Hypothesis</span>
          ) : null}
          {showReason && claim.reason ? <span className="mt-0.5 block text-xs text-zinc-600">{claim.reason}</span> : null}
        </span>
        <span className="shrink-0 pt-0.5 text-xs text-zinc-400">
          {claim.links.length} link{claim.links.length === 1 ? "" : "s"}
        </span>
      </button>
    </li>
  );
}
