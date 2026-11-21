import { useQuery } from "@tanstack/react-query";
import { api, post } from "./client";
import type { Job, JobList } from "./jobs";

export type StreamStatus = "queued" | "downloading" | "recording" | "processing" | "ready" | "failed";

export interface InspectResult {
  platform: "youtube" | "kick";
  external_video_id: string;
  title: string;
  channel: { external_id: string | null; name: string | null; known_channel_id: number | null };
  duration_ms: number | null;
  is_live: boolean;
  has_chat_replay: boolean;
  estimated_size_bytes: number | null;
  disk_free_bytes: number;
}

export interface Stream {
  id: number;
  title: string;
  platform: "youtube" | "kick" | "local";
  source_type: "vod_url" | "live_url" | "local_file";
  status: StreamStatus;
  duration_ms: number | null;
  error_message: string | null;
  created_at: string;
  channel_id: number | null;
  channel: { id: number; name: string } | null;
  storage: { source_bytes: number; rendered_bytes: number; source_deleted: boolean };
  clip_counts: Record<string, number>;
}

export interface StreamDetail extends Stream {
  source_url: string | null;
  detected_language: string | null;
  has_chat: boolean;
  suggested_layout_preset: { id: number; code: string } | null;
  active_jobs: Pick<Job, "id" | "job_type" | "status" | "progress_pct" | "stage" | "awaiting_confirmation">[];
}

export interface StreamList {
  items: Stream[];
  total: number;
}

export const STREAM_STATUS: Record<StreamStatus, { label: string; symbol: string; className: string }> = {
  queued: { label: "Menunggu", symbol: "○", className: "text-muted" },
  downloading: { label: "Mengunduh", symbol: "◐", className: "text-primary" },
  recording: { label: "Merekam", symbol: "●", className: "text-live" },
  processing: { label: "Diproses", symbol: "◐", className: "text-primary" },
  ready: { label: "Siap direview", symbol: "✓", className: "text-success" },
  failed: { label: "Gagal", symbol: "✕", className: "text-danger" },
};

export const PLATFORM_LABEL: Record<string, string> = { youtube: "YouTube", kick: "Kick", local: "File lokal" };

export const inspectStream = (url: string) => post<InspectResult>("/streams/inspect", { url });
export const importVod = (url: string) =>
  post<{ stream: Stream; job: Job }>("/streams", { url, mode: "vod" });

export function useStreams(limit = 50, status = "", offset = 0) {
  return useQuery({
    queryKey: ["streams", "list", limit, status, offset],
    queryFn: () =>
      api<StreamList>(`/streams?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`),
    placeholderData: (prev) => prev,
  });
}

export function useStream(id: number) {
  return useQuery({ queryKey: ["streams", id], queryFn: () => api<StreamDetail>(`/streams/${id}`) });
}

/** Semua Job satu Stream Sumber; ikut diperbarui SSE `job.updated` (kunci ["jobs", …]). */
export function useStreamJobs(id: number) {
  return useQuery({
    queryKey: ["jobs", "stream", id],
    queryFn: () => api<JobList>(`/jobs?source_stream_id=${id}&limit=200`),
  });
}
