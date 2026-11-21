import { PLATFORM_LABEL, STREAM_STATUS, useStream } from "../api/streams";
import { PipelineProgress } from "../components/PipelineProgress";
import { formatClock } from "../format";

/** P-04: sementara hanya header stream + progres pipeline; review Klip dibangun di T-041. */
export default function P04ReviewKlip({ params }: { params: Record<string, string> }) {
  const { data: stream, isLoading, isError } = useStream(Number(params.id));

  if (isLoading) return <p className="mx-auto max-w-5xl px-6 py-10 text-muted">Memuat stream…</p>;
  if (isError || !stream)
    return <p className="mx-auto max-w-5xl px-6 py-10 text-danger">Stream Sumber tidak ditemukan.</p>;

  const status = STREAM_STATUS[stream.status];
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
        {stream.status === "failed" && stream.error_message && (
          <p role="alert" className="rounded-input border border-danger/40 bg-danger/10 px-3 py-2">
            {stream.error_message}
          </p>
        )}
      </header>
      <p className="rounded-card border border-dashed border-border px-4 py-3 text-muted">
        Daftar Kandidat Klip belum tersedia di versi ini.
      </p>
    </section>
  );
}
