import { PLATFORM_LABEL, STREAM_STATUS, useStream } from "../api/streams";
import { useState } from "react";
import { Button } from "../components/Button";
import { PipelineProgress } from "../components/PipelineProgress";
import { UsageConfirmDialog } from "../components/UsageConfirmDialog";
import { formatClock } from "../format";

/** P-04: sementara hanya header stream + progres pipeline; review Klip dibangun di T-041. */
export default function P04ReviewKlip({ params }: { params: Record<string, string> }) {
  const { data: stream, isLoading, isError } = useStream(Number(params.id));
  const [confirming, setConfirming] = useState(false);

  if (isLoading) return <p className="mx-auto max-w-5xl px-6 py-10 text-muted">Memuat stream…</p>;
  if (isError || !stream)
    return <p className="mx-auto max-w-5xl px-6 py-10 text-danger">Stream Sumber tidak ditemukan.</p>;

  const status = STREAM_STATUS[stream.status];
  const held = stream.active_jobs.find((j) => j.job_type === "transcribe" && j.awaiting_confirmation);
  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-5xl space-y-4 px-6 py-8">
      <header className="space-y-2 rounded-card border border-border bg-surface p-4">
        <h1 id="page-title" className="text-xl font-semibold">{stream.title}</h1>
        <p className="text-muted">
          {[stream.channel?.name, PLATFORM_LABEL[stream.platform], formatClock(stream.duration_ms),
            stream.detected_language?.toUpperCase()].filter(Boolean).join(" · ")}
        </p>
        <p className={status.className}>
          <span aria-hidden="true">{status.symbol} </span>{status.label}
        </p>
        <PipelineProgress streamId={stream.id} />
        {held && (
          <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-input border border-warning/40 bg-warning/10 px-3 py-2">
            <p>Menunggu konfirmasi transkripsi.</p>
            <Button variant="primary" onClick={() => setConfirming(true)}>Lihat perkiraan pemakaian</Button>
          </div>
        )}
        {stream.status === "failed" && stream.error_message && (
          <p role="alert" className="rounded-input border border-danger/40 bg-danger/10 px-3 py-2">
            {stream.error_message}
          </p>
        )}
      </header>
      <p className="rounded-card border border-dashed border-border px-4 py-3 text-muted">
        Daftar Kandidat Klip belum tersedia di versi ini.
      </p>
      <UsageConfirmDialog job={confirming && held ? { id: held.id, stream_title: stream.title } : null}
        onClose={() => setConfirming(false)} />
    </section>
  );
}
