import { useEffect } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { TOKEN } from "./client";
import type { Job, JobList } from "./jobs";

const RETRY_MS = 3000;

function applyJobUpdate(qc: QueryClient, job: Partial<Job> & { id: number }) {
  let known = false;
  qc.setQueriesData<JobList>({ queryKey: ["jobs"] }, (list) => {
    if (!list?.items) return list;
    const items = list.items.map((j) => {
      if (j.id !== job.id) return j;
      known = true;
      return { ...j, ...job };
    });
    return { ...list, items };
  });
  qc.setQueryData<Job>(["job", job.id], (j) => (j ? { ...j, ...job } : j));
  // log_tail tidak ikut event: ambil ulang detail jika sedang dibuka.
  qc.invalidateQueries({ queryKey: ["job", job.id] });
  // Job baru atau keluar/masuk filter (mis. selesai): ambil ulang daftar dari REST.
  if (!known || job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
    qc.invalidateQueries({ queryKey: ["jobs"] });
  }
}

/** Langganan SSE /events; menyambung ulang otomatis dan memuat ulang data saat tersambung. */
export function useServerEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    let source: EventSource | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      source = new EventSource(`/api/v1/events?t=${encodeURIComponent(TOKEN)}`);
      source.onopen = () => qc.invalidateQueries();
      source.addEventListener("job.updated", (e) => applyJobUpdate(qc, JSON.parse((e as MessageEvent).data)));
      for (const name of ["stream.updated", "clip.created", "clip.updated", "upload.updated"]) {
        source.addEventListener(name, () => qc.invalidateQueries({ queryKey: [name.split(".")[0] + "s"] }));
      }
      source.onerror = () => {
        // EventSource menyambung ulang sendiri, kecuali koneksi ditutup (mis. server restart).
        if (source?.readyState === EventSource.CLOSED && !closed) {
          retry = window.setTimeout(connect, RETRY_MS);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      source?.close();
    };
  }, [qc]);
}
