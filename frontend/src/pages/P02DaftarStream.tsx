import { useState } from "react";
import { JOB_TYPE_LABEL, useActiveJobs } from "../api/jobs";
import { PLATFORM_LABEL, STREAM_STATUS, useStreams, type Stream } from "../api/streams";
import { Button } from "../components/Button";
import { formatBytes, formatClock } from "../format";

const PAGE_SIZE = 50;
const FILTERS = [
  { value: "", label: "Semua" },
  { value: "queued,downloading,recording,processing", label: "Diproses" },
  { value: "ready", label: "Siap direview" },
  { value: "failed", label: "Gagal" },
];

const CLIP_LABEL: [string, string][] = [
  ["candidate", "kandidat"],
  ["approved", "disetujui"],
  ["rendering", "dirender…"],
  ["rendered", "dirender"],
  ["render_failed", "render gagal"],
  ["rejected", "ditolak"],
];

function clipSummary(counts: Record<string, number>) {
  const parts = CLIP_LABEL.filter(([k]) => counts[k]).map(([k, label]) => `${counts[k]} ${label}`);
  return parts.length ? parts.join(" · ") : "–";
}

function StorageCell({ stream }: { stream: Stream }) {
  const { source_bytes, rendered_bytes, source_deleted } = stream.storage;
  return (
    <>
      <p className="font-medium">{formatBytes(source_bytes + rendered_bytes)}</p>
      <p className="text-xs text-muted">
        Sumber {source_deleted ? "dihapus" : formatBytes(source_bytes)} · Render {formatBytes(rendered_bytes)}
      </p>
    </>
  );
}

export default function P02DaftarStream() {
  const [filter, setFilter] = useState(FILTERS[0].value);
  const [offset, setOffset] = useState(0);
  const { data, isLoading, isError, refetch } = useStreams(PAGE_SIZE, filter, offset);
  const { data: active } = useActiveJobs();
  const runningFor = (id: number) =>
    active?.items.find((j) => j.source_stream_id === id && j.status === "running");

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 id="page-title" className="text-2xl font-semibold">Daftar Stream</h1>
        <a href="#/" className="text-muted hover:text-text hover:underline">Impor stream baru</a>
      </div>
      <p className="mt-1 text-muted">Semua Stream Sumber beserta status, jumlah klip, dan ukuran file.</p>

      <fieldset className="mt-6">
        <legend className="mb-1 text-xs text-muted">Status</legend>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => {
                setFilter(f.value);
                setOffset(0);
              }}
              className={`min-h-8 rounded-input border px-3 ${filter === f.value
                ? "border-primary bg-surface-2 text-text"
                : "border-border text-muted hover:border-muted hover:text-text"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="mt-4 overflow-x-auto rounded-card border border-border bg-surface">
        {isLoading && <p className="px-4 py-6 text-muted">Memuat daftar stream…</p>}
        {isError && (
          <div role="alert" className="flex items-center gap-3 px-4 py-6">
            <p className="text-danger">Daftar stream tidak bisa dimuat.</p>
            <Button onClick={() => refetch()}>Coba lagi</Button>
          </div>
        )}
        {data && items.length === 0 && (
          <p className="px-4 py-6 text-muted">
            {filter ? "Tidak ada stream dengan status ini." : "Belum ada stream. Impor link VOD dari Beranda."}
          </p>
        )}
        {items.length > 0 && (
          <table className="w-full min-w-[56rem] text-left">
            <caption className="sr-only">Stream Sumber</caption>
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="py-2 pr-3 pl-4 font-medium">Judul</th>
                <th scope="col" className="py-2 pr-3 font-medium">Kanal</th>
                <th scope="col" className="py-2 pr-3 font-medium">Platform</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">Durasi</th>
                <th scope="col" className="py-2 pr-3 font-medium">Status</th>
                <th scope="col" className="py-2 pr-3 font-medium">Klip</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Ukuran file</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const status = STREAM_STATUS[s.status];
                const job = runningFor(s.id);
                return (
                  <tr key={s.id} className="border-t border-border align-top hover:bg-surface-2">
                    <td className="max-w-80 py-3 pr-3 pl-4">
                      <a href={`#/streams/${s.id}`} className="block truncate font-medium hover:underline" title={s.title}>
                        {s.title}
                      </a>
                    </td>
                    <td className="max-w-48 truncate py-3 pr-3 text-muted">{s.channel?.name ?? "–"}</td>
                    <td className="py-3 pr-3 whitespace-nowrap text-muted">{PLATFORM_LABEL[s.platform]}</td>
                    <td className="py-3 pr-3 text-right whitespace-nowrap tabular-nums">{formatClock(s.duration_ms)}</td>
                    <td className="py-3 pr-3">
                      <p className={`whitespace-nowrap ${status.className}`}>
                        <span aria-hidden="true">{status.symbol} </span>{status.label}
                      </p>
                      {job && (
                        <p className="text-xs whitespace-nowrap text-muted">
                          {JOB_TYPE_LABEL[job.job_type] ?? job.job_type} {job.progress_pct}%
                        </p>
                      )}
                      {s.status === "failed" && s.error_message && (
                        <p className="max-w-56 truncate text-xs text-danger" title={s.error_message}>{s.error_message}</p>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-muted">{clipSummary(s.clip_counts)}</td>
                    <td className="py-3 pr-4 text-right whitespace-nowrap tabular-nums"><StorageCell stream={s} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {total > PAGE_SIZE && (
        <nav aria-label="Halaman daftar stream" className="mt-4 flex items-center justify-between">
          <p className="text-muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} dari {total}
          </p>
          <div className="flex gap-2">
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Sebelumnya</Button>
            <Button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Berikutnya</Button>
          </div>
        </nav>
      )}
    </section>
  );
}
