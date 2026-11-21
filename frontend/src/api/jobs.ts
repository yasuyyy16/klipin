import { useQuery } from "@tanstack/react-query";
import { api, post } from "./client";

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: number;
  job_type: string;
  status: JobStatus;
  source_stream_id: number | null;
  clip_id: number | null;
  scope_start_ms: number | null;
  awaiting_confirmation: boolean;
  progress_pct: number;
  stage: string | null;
  error_message: string | null;
  retry_of_job_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  stream_title: string | null;
}

export interface UsageEstimate {
  audio_ms: number;
  estimated_llm_windows: number;
  duration_ms: number;
  max_audio_ms: number;
  over_limit: boolean;
  pricing_links: { transcriber: string | null; llm: string | null };
}

export interface JobDetail extends Job {
  log_tail: string | null;
  usage_estimate: UsageEstimate | null;
}

export interface JobList {
  items: Job[];
  total: number;
}

export const JOB_TYPE_LABEL: Record<string, string> = {
  download: "Unduh",
  record_live: "Rekam live",
  transcribe: "Transkripsi",
  detect_layout: "Deteksi layout",
  score_highlights: "Skor highlight",
  render: "Render",
  upload: "Unggah",
};

export const activeJobsKey = ["jobs", "active"] as const;

export function useActiveJobs() {
  return useQuery({
    queryKey: activeJobsKey,
    queryFn: () => api<JobList>("/jobs?status=queued,running&limit=200"),
  });
}

export const cancelJob = (id: number) => post<Job>(`/jobs/${id}/cancel`);
export const retryJob = (id: number) => post<{ job: Job }>(`/jobs/${id}/retry`);
export const confirmJob = (id: number, proceed: boolean,
  range: { start_ms: number; end_ms: number } | null = null) =>
  post<Job>(`/jobs/${id}/confirm`, { proceed, range });

export function useJobs(status: string) {
  return useQuery({
    queryKey: ["jobs", "list", status],
    queryFn: () => api<JobList>(`/jobs?limit=200${status ? `&status=${status}` : ""}`),
  });
}

export function useJobDetail(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api<JobDetail>(`/jobs/${id}`),
    enabled,
  });
}
