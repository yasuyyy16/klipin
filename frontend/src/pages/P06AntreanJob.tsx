import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import {
  cancelJob, retryJob, useJobDetail, useJobs, JOB_TYPE_LABEL,
  type Job, type JobStatus,
} from "../api/jobs";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { UsageConfirmDialog } from "../components/UsageConfirmDialog";
import { useToast } from "../components/Toast";

const FILTERS = [
  { value: "queued,running", label: "Aktif" },
  { value: "", label: "Semua" },
  { value: "failed", label: "Gagal" },
  { value: "succeeded", label: "Selesai" },
  { value: "cancelled", label: "Dibatalkan" },
];

// Status selalu berupa teks + simbol, bukan warna saja (08-ui-ux.md §6).
const STATUS: Record<JobStatus, { label: string; symbol: string; className: string }> = {
  queued: { label: "Menunggu", symbol: "○", className: "text-muted" },
  running: { label: "Berjalan", symbol: "◐", className: "text-primary" },
  succeeded: { label: "Selesai", symbol: "✓", className: "text-success" },
  failed: { label: "Gagal", symbol: "✕", className: "text-danger" },
  cancelled: { label: "Dibatalkan", symbol: "–", className: "text-muted" },
};

function parseUtc(iso: string | null) {
  return iso ? new Date(iso).getTime() : null;
}

function formatTime(iso: string | null) {
  const t = parseUtc(iso);
  return t ? new Date(t).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "medium" }) : "–";
}

function formatDuration(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h} j ${m} mnt` : m ? `${m} mnt ${sec} dtk` : `${sec} dtk`;
}

/** Jam yang berdetak tiap detik selama ada Job berjalan (untuk kolom durasi). */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function errorText(err: unknown) {
  return err instanceof ApiError ? err.message : "Terjadi kesalahan di Klipin. Detail ada di log.";
}

function JobLog({ job }: { job: Job }) {
  const { data, isLoading, isError } = useJobDetail(job.id, true);
  return (
    <div className="space-y-3 px-4 pb-4">
      {job.error_message && (
        <p className="rounded-input border border-danger/40 bg-danger/10 px-3 py-2 text-text">
          <span className="font-medium text-danger">Error: </span>{job.error_message}
        </p>
      )}
      {isLoading && <p className="text-muted">Memuat log…</p>}
      {isError && <p className="text-danger">Log tidak bisa dimuat.</p>}
      {data && (
        <pre className="max-h-64 overflow-auto rounded-input bg-bg p-3 font-mono text-xs whitespace-pre-wrap text-muted">
          {data.log_tail?.trim() || "Belum ada log untuk Job ini."}
        </pre>
      )}
    </div>
  );
}

function JobRow({ job, now, onCancel, onRetry, onConfirm, busy }: {
  job: Job;
  now: number;
  onCancel: (job: Job) => void;
  onRetry: (job: Job) => void;
  onConfirm: (job: Job) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const status = job.awaiting_confirmation && job.status === "queued"
    ? { label: "Menunggu konfirmasi", symbol: "!", className: "text-warning" }
    : STATUS[job.status];
  const started = parseUtc(job.started_at);
  const finished = parseUtc(job.finished_at);
  const duration = started ? formatDuration((finished ?? now) - started) : "–";
  const object = job.stream_title ?? (job.clip_id ? `Klip #${job.clip_id}` : "–");
  const detailId = `job-detail-${job.id}`;

  return (
    <>
      <tr className="border-t border-border align-middle">
        <td className="py-3 pr-3 pl-4">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={detailId}
            onClick={() => setOpen((o) => !o)}
            className="flex min-h-8 items-center gap-2 rounded-input px-2 text-left hover:bg-surface-2"
          >
            <span aria-hidden="true" className={`inline-block transition-transform ${open ? "rotate-90" : ""}`}>›</span>
            <span className="font-medium">{JOB_TYPE_LABEL[job.job_type] ?? job.job_type}</span>
            <span className="sr-only">{open ? "Sembunyikan log" : "Tampilkan log"}</span>
          </button>
        </td>
        <td className="max-w-64 truncate py-3 pr-3" title={object}>{object}</td>
        <td className={`py-3 pr-3 whitespace-nowrap ${status.className}`}>
          <span aria-hidden="true">{status.symbol} </span>{status.label}
        </td>
        <td className="w-56 py-3 pr-3">
          <div
            role="progressbar"
            aria-label={`Progres ${JOB_TYPE_LABEL[job.job_type] ?? job.job_type}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={job.progress_pct}
            className="h-1.5 overflow-hidden rounded-full bg-surface-2"
          >
            <div className="h-full bg-primary transition-[width]" style={{ width: `${job.progress_pct}%` }} />
          </div>
          <p className="mt-1 truncate text-xs text-muted">
            {job.progress_pct}%{job.stage ? ` · ${job.stage}` : ""}
          </p>
        </td>
        <td className="py-3 pr-3 whitespace-nowrap text-muted">{formatTime(job.started_at)}</td>
        <td className="py-3 pr-3 whitespace-nowrap text-muted">{duration}</td>
        <td className="py-3 pr-4 text-right whitespace-nowrap">
          {job.awaiting_confirmation && job.status === "queued" && (
            <Button variant="primary" className="mr-2" onClick={() => onConfirm(job)} disabled={busy}>
              Konfirmasi pemakaian
            </Button>
          )}
          {(job.status === "queued" || job.status === "running") && (
            <Button onClick={() => onCancel(job)} disabled={busy}>Batalkan</Button>
          )}
          {(job.status === "failed" || job.status === "cancelled") && (
            <Button onClick={() => onRetry(job)} disabled={busy}>Coba lagi</Button>
          )}
        </td>
      </tr>
      {open && (
        <tr id={detailId} className="bg-surface">
          <td colSpan={7}><JobLog job={job} /></td>
        </tr>
      )}
    </>
  );
}

export default function P06AntreanJob() {
  const [filter, setFilter] = useState(FILTERS[0].value);
  const [type, setType] = useState("");
  const { data, isLoading, isError, refetch } = useJobs(filter);
  const qc = useQueryClient();
  const toast = useToast();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [toCancel, setToCancel] = useState<Job | null>(null);
  const [toConfirm, setToConfirm] = useState<Job | null>(null);

  const items = (data?.items ?? []).filter((j) => !type || j.job_type === type);
  const now = useNow(items.some((j) => j.status === "running"));

  async function run(job: Job, action: () => Promise<unknown>, success: string) {
    setBusyId(job.id);
    try {
      await action();
      toast(success, "success");
      await qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      setBusyId(null);
    }
  }

  const emptyText = filter === "queued,running"
    ? "Tidak ada Job berjalan."
    : "Tidak ada Job dengan filter ini.";

  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-6xl px-6 py-8">
      <h1 id="page-title" className="text-2xl font-semibold">Antrean Job</h1>
      <p className="mt-1 text-muted">Progres unduh, transkripsi, deteksi layout, skor, render, dan unggah.</p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <fieldset>
          <legend className="mb-1 text-xs text-muted">Status</legend>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                aria-pressed={filter === f.value}
                onClick={() => setFilter(f.value)}
                className={`min-h-8 rounded-input border px-3 ${filter === f.value
                  ? "border-primary bg-surface-2 text-text"
                  : "border-border text-muted hover:border-muted hover:text-text"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </fieldset>
        <div>
          <label htmlFor="job-type" className="mb-1 block text-xs text-muted">Jenis</label>
          <select
            id="job-type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="min-h-8 rounded-input border border-border bg-surface-2 px-2"
          >
            <option value="">Semua jenis</option>
            {Object.entries(JOB_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto rounded-card border border-border bg-surface">
        {isLoading && <p className="px-4 py-6 text-muted">Memuat daftar Job…</p>}
        {isError && (
          <div className="flex items-center gap-3 px-4 py-6">
            <p className="text-danger">Daftar Job tidak bisa dimuat. Pastikan Klipin masih berjalan.</p>
            <Button onClick={() => refetch()}>Muat ulang</Button>
          </div>
        )}
        {data && items.length === 0 && <p className="px-4 py-6 text-muted">{emptyText}</p>}
        {items.length > 0 && (
          <table className="w-full min-w-[56rem] text-left">
            <caption className="sr-only">Daftar Job</caption>
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="py-2 pr-3 pl-6 font-medium">Jenis</th>
                <th scope="col" className="py-2 pr-3 font-medium">Objek</th>
                <th scope="col" className="py-2 pr-3 font-medium">Status</th>
                <th scope="col" className="py-2 pr-3 font-medium">Progres</th>
                <th scope="col" className="py-2 pr-3 font-medium">Mulai</th>
                <th scope="col" className="py-2 pr-3 font-medium">Durasi</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {items.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  now={now}
                  busy={busyId === job.id}
                  onCancel={setToCancel}
                  onRetry={(j) => run(j, () => retryJob(j.id), "Job dicoba lagi.")}
                  onConfirm={setToConfirm}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
      {data && data.total > data.items.length && (
        <p className="mt-2 text-xs text-muted">Menampilkan {data.items.length} Job terbaru dari {data.total}.</p>
      )}

      <ConfirmDialog
        open={toCancel !== null}
        title="Batalkan Job?"
        message={toCancel
          ? `${JOB_TYPE_LABEL[toCancel.job_type] ?? toCancel.job_type} untuk "${toCancel.stream_title ?? "Job ini"}" akan dihentikan. Kamu bisa mencobanya lagi nanti.`
          : ""}
        confirmLabel="Batalkan Job"
        danger
        busy={busyId !== null}
        onCancel={() => setToCancel(null)}
        onConfirm={async () => {
          if (toCancel) await run(toCancel, () => cancelJob(toCancel.id), "Job dibatalkan.");
          setToCancel(null);
        }}
      />

      <UsageConfirmDialog job={toConfirm} onClose={() => setToConfirm(null)} />
    </section>
  );
}
