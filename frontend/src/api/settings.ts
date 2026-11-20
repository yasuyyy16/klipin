import { useQuery } from "@tanstack/react-query";
import { api, del, patch, post, put } from "./client";

export type SecretName = "transcriber_api_key" | "llm_api_key";

export interface Settings {
  score_weights: { audio: number; chat: number; llm: number };
  score_min_threshold: number;
  chat_delay_ms: number;
  chat_reaction_words: string[];
  live_segment_seconds: number;
  live_block_minutes: number;
  live_last_n_default_s: number;
  max_heavy_jobs: number;
  confirm_usage_over_min: number;
  max_audio_minutes_per_job: number;
  transcriber_provider: "deepgram" | "assemblyai";
  llm_provider: "anthropic";
  llm_models: { judge_highlight: string | null; translate_lines: string | null; write_captions: string | null };
  kick_live_chat_enabled: boolean;
  upload_default_mode: "manual" | "auto";
  output_dir: string;
  download_max_height: number;
  secrets: Record<SecretName, { set: boolean; masked: string | null }>;
  storage: { keyring_available: boolean };
}

export interface SecretTest {
  ok: boolean;
  provider: string;
  latency_ms: number | null;
  error: string | null;
}

export interface Health {
  ok: boolean;
  checks: { name: string; ok: boolean; detail: string }[];
  home: string;
  backup_dir: string;
}

export interface YtdlpUpdate {
  updated: boolean;
  version_before: string | null;
  version_after: string | null;
  message: string;
}

export const settingsKey = ["settings"] as const;

export const useSettings = () => useQuery({ queryKey: settingsKey, queryFn: () => api<Settings>("/settings") });
export const useHealth = () =>
  useQuery({ queryKey: ["system", "health"], queryFn: () => api<Health>("/system/health") });

export const saveSettings = (changes: Partial<Settings>) => patch<Settings>("/settings", changes);
export const saveSecret = (name: SecretName, value: string) => put(`/secrets/${name}`, { value });
export const deleteSecret = (name: SecretName) => del(`/secrets/${name}`);
export const testSecret = (name: SecretName) => post<SecretTest>(`/secrets/${name}/test`);
export const updateYtdlp = () => post<YtdlpUpdate>("/system/update-ytdlp");
