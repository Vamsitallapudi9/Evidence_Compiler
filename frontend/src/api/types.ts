// API contract types for the Evidence Compiler backend (all routes under /api).

export type SourceKind = "pdf" | "csv" | "xlsx" | "postgres" | "web" | "docx" | "text" | "huggingface";

export interface SourceOut {
  id: string;
  kind: SourceKind;
  name: string;
  ingested_at: string;
  evidence_count: number;
  tables: string[];
  flagged_count: number;
  page_count?: number | null;
  /** Original link, or `https://huggingface.co/datasets/<name>` for Hugging Face sources. */
  url?: string | null;
  license?: string | null;
  fetched_at?: string | null;
}

export interface PdfLocation {
  kind: "pdf";
  page: number;
  char_start: number;
  char_end: number;
  table_index?: number | null;
  row_index?: number | null;
}

/**
 * A span in a web page, Word document or text file. `page` is a section number
 * (web pages always have a single section); offsets index into that section's
 * canonical text as served by `GET /api/sources/{id}/pages/{page}`.
 */
export interface TextLocation {
  kind: "text";
  page: number;
  char_start: number;
  char_end: number;
}

export interface TableLocation {
  kind: "table";
  table: string;
  sheet?: string | null;
  row_index: number;
  columns: string[];
}

export interface QueryLocation {
  kind: "query";
  engine: "duckdb" | "postgres";
  sql: string;
  tables: string[];
  executed_at: string;
  row_count: number;
  row_index: number;
}

export interface CalcLocation {
  kind: "calc";
  calculation_id: string;
}

export type Location = PdfLocation | TextLocation | TableLocation | QueryLocation | CalcLocation;

export type FieldValue = string | number | boolean | null;

export interface EvidenceItem {
  id: string;
  source_ids: string[];
  origin: "primary" | "derived";
  creator: "connector" | "sql" | "calc";
  text: string;
  fields: Record<string, FieldValue>;
  location: Location;
  derived_from: string[];
  calculation_id?: string | null;
  security_flags: string[];
  metadata: Record<string, unknown>;
}

export interface ResolvedInput {
  name: string;
  evidence_id: string;
  field?: string | null;
  quote?: string | null;
  /** Decimal serialized as a string. */
  value: string;
  unit?: string | null;
}

export type CalcOp = "difference" | "pct_change" | "ratio" | "share_of_total" | "sum" | "mean";

export interface Calculation {
  id: string;
  op: CalcOp;
  inputs: ResolvedInput[];
  /** Decimal serialized as a string. */
  result: string;
  unit?: string | null;
  formula: string;
  output_evidence_id: string;
}

export type ClaimType = "primary" | "derived" | "interpretation" | "unsupported";
export type ClaimStatus = "supported" | "partial" | "unsupported" | "rejected";

export type Relation =
  | "supports"
  | "contradicts"
  | "derived_from"
  | "calculated_from"
  | "inferred_from"
  | "depends_on"
  | "supersedes";

export interface EvidenceLink {
  evidence_id: string;
  relation: Relation;
  quote?: string | null;
  quote_span?: [number, number] | null;
}

export interface CheckResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Claim {
  id: string;
  text: string;
  type: ClaimType;
  status: ClaimStatus;
  links: EvidenceLink[];
  calculation_id?: string | null;
  checks: CheckResult[];
  entailment?: "supports" | "partial" | "does_not_support" | null;
  entailment_note?: string | null;
  reason: string;
  origin: "answer" | "hypothesis";
}

export interface Source {
  id: string;
  kind: SourceKind;
  name: string;
  uri: string;
  content_hash: string;
  ingested_at: string;
  metadata: Record<string, unknown>;
}

export type GraphNodeKind = "question" | "claim" | "evidence" | "calculation" | "source";

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface Answer {
  run_id: string;
  question: string;
  text: string;
  insufficient: boolean;
  claims: Claim[];
  gaps: string[];
  evidence: Record<string, EvidenceItem>;
  calculations: Record<string, Calculation>;
  sources: Record<string, Source>;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  warnings: string[];
  created_at: string;
}

export type RunStatus = "pending" | "running" | "done" | "failed" | "cancelled";

/** One model call made by a run. Streamed as SSE `llm` events (once at start, once at the end; upsert by id). */
export interface LlmCall {
  id: string;
  /** plan | sql | sql_repair | claims | verify | compile | (others) */
  task: string;
  /** Human text, e.g. "Verifying claim 3 of 20". */
  label: string;
  model: string;
  status: "running" | "ok" | "error" | "cached";
  /** ISO timestamp. */
  started_at: string;
  /** Null while running. */
  seconds: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  error?: string | null;
}

export interface RunUsage {
  /** e.g. "openai". */
  provider: string;
  /** e.g. "gpt-6-luna"; "a + b" when model tiers differ. */
  model: string;
  /** Every call started so far (including in-flight, failed and cached ones). */
  calls: number;
  in_flight: number;
  failed_calls: number;
  cache_hits: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cached_input_tokens: number;
  /** Null when pricing is not configured. */
  est_cost_usd: number | null;
  /** Present in `GET /api/runs/{id}`; omitted in heartbeats. */
  calls_log?: LlmCall[];
}

/** SSE `heartbeat` event, sent every ~2s while a run is in progress. */
export interface RunHeartbeat {
  run_id: string;
  status: RunStatus;
  /** A worker is actually executing this run. */
  alive: boolean;
  elapsed_s: number;
  /** Seconds since the last progress event or LLM call start/end. */
  last_activity_s: number;
  /** Label of the newest in-flight LLM call, else the latest progress message. */
  current: string | null;
  usage: RunUsage;
}

export interface RunEvent {
  stage: string;
  message: string;
  data: Record<string, unknown>;
  ts: string;
}

export interface RunOut {
  id: string;
  question: string;
  status: RunStatus;
  error?: string | null;
  created_at: string;
  events: RunEvent[];
  answer?: Answer | null;
  usage?: RunUsage | null;
  /** A worker is actually executing this run (false after a server restart, for example). */
  alive?: boolean;
}

export interface RunSummary {
  id: string;
  question: string;
  status: RunStatus;
  created_at: string;
  /** Optional: lets the runs list tell interrupted runs ("Interrupted: …") from other failures. */
  error?: string | null;
}

export interface PageText {
  page: number;
  text: string;
  page_count: number;
}

export interface Health {
  status: "ok";
  llm_configured: boolean;
  llm_provider: string;
  llm_model: string;
  pricing_configured: boolean;
}

export interface PostgresSourceIn {
  name: string;
  dsn: string;
  schema?: string;
}

export interface UrlSourceIn {
  url: string;
  name?: string;
}

export interface HuggingFaceSourceIn {
  /** "owner/name" (or a legacy single-segment name). */
  dataset: string;
  config?: string;
  split?: string;
  max_rows?: number;
}
