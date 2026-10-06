import type { ReactNode } from "react";
import { useHealth } from "../api/hooks";

export function Layout({ sidebar, children, health }: { sidebar: ReactNode; children: ReactNode; health?: ReactNode }) {
  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5 py-3">
        <div className="min-w-0">
          <h1 className="text-base font-semibold tracking-tight text-zinc-900">Evidence Compiler</h1>
          <p className="truncate text-xs text-zinc-500">
            Answers where every claim is traced to a source, a calculation, or labeled as interpretation.
          </p>
        </div>
        {health ?? (
          <div className="flex shrink-0 items-center gap-2">
            <HealthModelChip />
            <HealthIndicator />
          </div>
        )}
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 space-y-6 overflow-y-auto border-r border-zinc-200 bg-zinc-50/60 p-4" aria-label="Sources and runs">
          {sidebar}
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto px-6 py-6">{children}</main>
      </div>
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return <span aria-hidden="true" className={`inline-block size-2 rounded-full ${color}`} />;
}

export function HealthIndicator() {
  const { data, error, isLoading } = useHealth();
  let content: ReactNode;
  if (isLoading) content = <><Dot color="bg-zinc-300" /> Checking API…</>;
  else if (error || !data) content = <><Dot color="bg-red-500" /> API offline</>;
  else if (data.llm_configured) content = <><Dot color="bg-emerald-500" /> API online · LLM configured</>;
  else content = <><Dot color="bg-amber-500" /> API online · LLM not configured</>;
  return (
    <p role="status" className="flex shrink-0 items-center gap-1.5 rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600">
      {content}
    </p>
  );
}

/** Monospace "provider · model" chip for the LLM in use. */
export function ModelChip({ provider, model, pricingConfigured = true }: { provider?: string; model: string; pricingConfigured?: boolean }) {
  const label = provider ? `${provider} · ${model}` : model;
  return (
    <p
      className="max-w-72 shrink-0 truncate rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 font-mono text-xs text-zinc-700"
      title={`LLM in use: ${label}${pricingConfigured ? "" : " · cost estimates off (no pricing configured)"}`}
    >
      {label}
    </p>
  );
}

function HealthModelChip() {
  const { data } = useHealth();
  if (!data?.llm_model) return null;
  return <ModelChip provider={data.llm_provider} model={data.llm_model} pricingConfigured={data.pricing_configured !== false} />;
}

export function StaticIndicator({ label }: { label: string }) {
  return (
    <p className="flex shrink-0 items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs text-violet-800">
      <Dot color="bg-violet-500" /> {label}
    </p>
  );
}
