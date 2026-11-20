import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: number;
  job_type: string;
  status: JobStatus;
  source_stream_id: number | null;
  clip_id: number | null;
  awaiting_confirmation: boolean;
  progress_pct: number;
  stage: string | null;
  error_message: string | null;
  retry_of_job_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface JobDetail extends Job {
  log_tail: string | null;
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
