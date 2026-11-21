import type { Job } from "../api/jobs";
import { useStreamJobs } from "../api/streams";

/** Tahap pipeline Stream Sumber (08-ui-ux.md P-04): Unduh · Layout · Transkripsi · Skor. */
const STAGES = [
  { types: ["download", "record_live"], label: "Unduh" },
  { types: ["detect_layout"], label: "Layout" },
  { types: ["transcribe"], label: "Transkripsi" },
  { types: ["score_highlights"], label: "Skor" },
];

function stageState(job: Job | undefined) {
  if (!job) return { text: "", symbol: "○", className: "text-muted", sr: "belum mulai" };
  if (job.status === "queued" && job.awaiting_confirmation)
    return { text: "", symbol: "!", className: "text-warning", sr: "menunggu konfirmasi" };
  switch (job.status) {
    case "succeeded":
      return { text: "", symbol: "✓", className: "text-success", sr: "selesai" };
    case "running":
      return { text: `${job.progress_pct}%`, symbol: "◐", className: "text-primary", sr: "berjalan" };
    case "failed":
      return { text: "", symbol: "✕", className: "text-danger", sr: "gagal" };
    case "cancelled":
      return { text: "", symbol: "–", className: "text-muted", sr: "dibatalkan" };
    default:
      return { text: "", symbol: "○", className: "text-muted", sr: "menunggu" };
  }
}

export function PipelineProgress({ streamId }: { streamId: number }) {
  const { data } = useStreamJobs(streamId);
  // Job terbaru per tahap (daftar dari API sudah urut terbaru dulu); abaikan Job berrentang.
  const latest = (types: string[]) =>
    data?.items.find((j) => types.includes(j.job_type) && j.scope_start_ms === null);

  return (
    <ol aria-label="Progres pipeline" className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {STAGES.map((stage, i) => {
        const job = latest(stage.types);
        const s = stageState(job);
        return (
          <li key={stage.label} className="flex items-center gap-2">
            {i > 0 && <span aria-hidden="true" className="text-muted">·</span>}
            <span className={s.className}>
              {stage.label} {s.text || <span aria-hidden="true">{s.symbol}</span>}
              <span className="sr-only"> ({s.sr})</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
