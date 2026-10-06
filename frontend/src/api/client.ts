import type {
  EvidenceItem,
  Health,
  HuggingFaceSourceIn,
  PageText,
  PostgresSourceIn,
  RunOut,
  RunSummary,
  SourceOut,
  UrlSourceIn,
} from "./types";

export const API_BASE = "/api";

/** Error raised for non-2xx responses and network failures. */
export class ApiError extends Error {
  /** HTTP status; 0 means the request never reached the server. */
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

/** Extracts a readable message from a FastAPI-style `{detail}` error body. */
function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg, type}, ...]
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter((m): m is string => Boolean(m));
    if (msgs.length) return msgs.join("; ");
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Cannot reach the backend. Is the API server running?", 0);
  }

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`.trim();
    let fromBody: string | null = null;
    try {
      fromBody = detailMessage(await res.json());
      if (fromBody) message = fromBody;
    } catch {
      // non-JSON body; keep status text
    }
    // The Vite proxy answers 502/504 with an empty body when the backend is down. A 502 that
    // carries a `{detail}` comes from the backend itself (e.g. fetching a linked URL failed).
    const status = (res.status === 502 || res.status === 504) && !fromBody ? 0 : res.status;
    if (status === 0) message = "Cannot reach the backend. Is the API server running?";
    throw new ApiError(message, status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/health"),

  listSources: () => request<SourceOut[]>("/sources"),
  uploadSource: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<SourceOut>("/sources", { method: "POST", body: form });
  },
  addPostgres: (body: PostgresSourceIn) => postJson<SourceOut>("/sources/postgres", body),
  addUrl: (body: UrlSourceIn) => postJson<SourceOut>("/sources/url", body),
  addHuggingFace: (body: HuggingFaceSourceIn) => postJson<SourceOut>("/sources/huggingface", body),
  deleteSource: (id: string) => request<void>(`/sources/${enc(id)}`, { method: "DELETE" }),
  getPage: (sourceId: string, page: number) =>
    request<PageText>(`/sources/${enc(sourceId)}/pages/${page}`),

  createRun: (question: string) => postJson<{ run_id: string }>("/runs", { question }),
  listRuns: () => request<RunSummary[]>("/runs"),
  getRun: (id: string) => request<RunOut>(`/runs/${enc(id)}`),
  /** 202 `{status: "cancelling"}`; 409 if the run already finished. Takes effect at the next step boundary. */
  cancelRun: (id: string) => request<{ status: string }>(`/runs/${enc(id)}/cancel`, { method: "POST" }),
  runEventsUrl: (id: string) => `${API_BASE}/runs/${enc(id)}/events`,

  getEvidence: (id: string) => request<EvidenceItem>(`/evidence/${enc(id)}`),
};

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
