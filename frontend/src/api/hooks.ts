import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "./client";
import type { EvidenceItem, HuggingFaceSourceIn, PostgresSourceIn, RunOut, UrlSourceIn } from "./types";

export const queryKeys = {
  health: ["health"] as const,
  sources: ["sources"] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  evidence: (id: string) => ["evidence", id] as const,
  page: (sourceId: string, page: number) => ["sources", sourceId, "pages", page] as const,
};

export function isTerminal(status: RunOut["status"] | undefined): boolean {
  return status === "done" || status === "failed" || status === "cancelled";
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    // Poll faster while the backend is unreachable so the UI recovers quickly.
    refetchInterval: (query) => (query.state.status === "error" ? 5_000 : 30_000),
    retry: false,
  });
}

/** When the backend comes back online, refetch every query that failed while it was down. */
export function useRecoverOnReconnect() {
  const qc = useQueryClient();
  const { isSuccess } = useHealth();
  useEffect(() => {
    if (isSuccess) void qc.invalidateQueries({ predicate: (q) => q.state.status === "error" });
  }, [isSuccess, qc]);
}

export function useSources() {
  return useQuery({ queryKey: queryKeys.sources, queryFn: api.listSources });
}

export function useUploadSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadSource(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useAddPostgres() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PostgresSourceIn) => api.addPostgres(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useAddUrl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UrlSourceIn) => api.addUrl(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useAddHuggingFace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HuggingFaceSourceIn) => api.addHuggingFace(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteSource(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

export function useRuns() {
  return useQuery({ queryKey: queryKeys.runs, queryFn: api.listRuns });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (question: string) => api.createRun(question),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.runs }),
  });
}

/** Requests cancellation; the run ends as "cancelled" at its next step boundary. */
export function useCancelRun(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelRun(runId),
    // Refresh either way: a 409 means the run already finished.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void qc.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

/**
 * Fetches a run. While the run is in flight we poll slowly as a fallback;
 * live progress comes from SSE (useRunEvents), which triggers a refetch on `done`.
 */
export function useRun(id: string | null) {
  return useQuery({
    queryKey: queryKeys.run(id ?? ""),
    queryFn: () => api.getRun(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 5_000),
  });
}

/**
 * Evidence lookup: prefer the copy embedded in the answer, otherwise fetch it.
 */
export function useEvidence(id: string, embedded: EvidenceItem | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.evidence(id),
    queryFn: () => api.getEvidence(id),
    enabled: enabled && !embedded,
    initialData: embedded,
    staleTime: Infinity,
  });
}

export function usePageText(sourceId: string | undefined, page: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.page(sourceId ?? "", page),
    queryFn: () => api.getPage(sourceId as string, page),
    enabled: enabled && Boolean(sourceId),
    staleTime: Infinity,
  });
}
