import type { ClaimStatus, ClaimType } from "../api/types";

interface TypeStyle {
  label: string;
  short: string;
  description: string;
  /** Badge chip classes. */
  badge: string;
  /** Inline answer span classes (color + underline style, so type is not color-only). */
  span: string;
  /** Graph node colors. */
  node: { bg: string; border: string };
}

export const CLAIM_TYPE_STYLES: Record<ClaimType, TypeStyle> = {
  primary: {
    label: "Primary",
    short: "P",
    description: "Stated directly in a source passage or row.",
    badge: "bg-blue-50 text-blue-800 ring-blue-200",
    span: "decoration-blue-600 decoration-solid hover:bg-blue-50 text-blue-950",
    node: { bg: "#eff6ff", border: "#2563eb" },
  },
  derived: {
    label: "Derived",
    short: "D",
    description: "Computed deterministically from evidence (SQL or calculation).",
    badge: "bg-teal-50 text-teal-800 ring-teal-200",
    span: "decoration-teal-600 decoration-double hover:bg-teal-50 text-teal-950",
    node: { bg: "#f0fdfa", border: "#0d9488" },
  },
  interpretation: {
    label: "AI interpretation",
    short: "AI",
    description: "Model reasoning over evidence; not itself evidence.",
    badge: "bg-amber-50 text-amber-900 ring-amber-200",
    span: "decoration-amber-600 decoration-dotted hover:bg-amber-50 text-amber-950",
    node: { bg: "#fffbeb", border: "#d97706" },
  },
  unsupported: {
    label: "Unsupported",
    short: "U",
    description: "No adequate evidence was found; shown so the gap is explicit.",
    badge: "bg-rose-50 text-rose-800 ring-rose-200",
    span: "decoration-rose-600 decoration-wavy hover:bg-rose-50 text-rose-950",
    node: { bg: "#fff1f2", border: "#e11d48" },
  },
};

export const CLAIM_STATUS_STYLES: Record<ClaimStatus, { label: string; badge: string; icon: string }> = {
  supported: { label: "Supported", badge: "bg-emerald-50 text-emerald-800 ring-emerald-200", icon: "✓" },
  partial: { label: "Partial", badge: "bg-yellow-50 text-yellow-900 ring-yellow-300", icon: "◐" },
  unsupported: { label: "Unsupported", badge: "bg-rose-50 text-rose-800 ring-rose-200", icon: "✕" },
  rejected: { label: "Rejected", badge: "bg-zinc-100 text-zinc-700 ring-zinc-300", icon: "⊘" },
};

export function isProblemStatus(status: ClaimStatus): boolean {
  return status === "unsupported" || status === "rejected";
}
