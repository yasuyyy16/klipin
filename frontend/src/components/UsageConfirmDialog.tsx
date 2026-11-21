import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { confirmJob, useJobDetail } from "../api/jobs";
import { formatClock, formatDurationWords, parseClock } from "../format";
import { Button } from "./Button";
import { Field, inputClass } from "./Field";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

/** Dialog FR-022: durasi audio, perkiraan jendela AI, tautan harga, proses semua / rentang. */
export function UsageConfirmDialog({ job, onClose }: {
  job: { id: number; stream_title: string | null } | null;
  onClose: () => void;
}) {
  return (
    <Modal open={job !== null} onClose={onClose} title="Konfirmasi pemakaian API">
      {job && <DialogBody key={job.id} job={job} onClose={onClose} />}
    </Modal>
  );
}

function DialogBody({ job, onClose }: { job: { id: number; stream_title: string | null }; onClose: () => void }) {
  const { data, isLoading, isError } = useJobDetail(job.id, true);
  const qc = useQueryClient();
  const toast = useToast();
  const est = data?.usage_estimate ?? null;
  const [mode, setMode] = useState<"all" | "range" | null>(null);
  const [start, setStart] = useState("0:00:00");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (isLoading) return <p className="text-muted">Memuat perkiraan pemakaian…</p>;
  if (isError || !data) return <p className="text-danger">Perkiraan pemakaian tidak bisa dimuat.</p>;
  if (!est) return <p className="text-muted">Job ini tidak lagi menunggu konfirmasi.</p>;

  const chosen = mode ?? (est.over_limit ? "range" : "all");
  const endText = end || formatClock(Math.min(est.duration_ms, est.max_audio_ms));

  const submit = async () => {
    setError(null);
    let range = null;
    if (chosen === "range") {
      const s = parseClock(start);
      const e = parseClock(endText);
      if (s === null || e === null) {
        setError("Tulis waktu sebagai jam:menit:detik, mis. 0:45:00.");
        return;
      }
      range = { start_ms: s, end_ms: e };
    }
    setBusy(true);
    try {
      await confirmJob(job.id, true, range);
      toast("Transkripsi dilanjutkan.", "success");
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Konfirmasi gagal. Detail ada di log.");
    } finally {
      setBusy(false);
    }
  };

  const links = [
    ["transkripsi", est.pricing_links.transcriber],
    ["LLM", est.pricing_links.llm],
  ].filter(([, href]) => href) as [string, string][];

  return (
    <div className="space-y-4">
      <p>
        Audio yang dikirim ke API transkripsi untuk "{job.stream_title ?? "stream ini"}":{" "}
        <strong>{formatDurationWords(est.audio_ms)}</strong> (±{est.estimated_llm_windows} jendela dinilai AI).
        Cek harga di situs penyedia. Lanjutkan?
      </p>
      {links.length > 0 && (
        <p className="text-muted">
          Halaman harga:{" "}
          {links.map(([label, href], i) => (
            <span key={label}>
              {i > 0 && " · "}
              <a href={href} target="_blank" rel="noreferrer" className="text-text underline">{label}</a>
            </span>
          ))}
        </p>
      )}
      {est.over_limit && (
        <p role="status" className="rounded-input border border-warning/40 bg-warning/10 px-3 py-2">
          Durasi melebihi batas per Job ({formatDurationWords(est.max_audio_ms)}). Pilih rentang waktu,
          atau naikkan batas di Pengaturan.
        </p>
      )}

      <fieldset className="space-y-2">
        <legend className="sr-only">Bagian yang ditranskripsi</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="usage-mode" checked={chosen === "all"} disabled={est.over_limit}
            onChange={() => setMode("all")} />
          Proses semua ({formatDurationWords(est.duration_ms)})
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="usage-mode" checked={chosen === "range"} onChange={() => setMode("range")} />
          Rentang tertentu saja
        </label>
      </fieldset>
      {chosen === "range" && (
        <div className="grid grid-cols-2 gap-4">
          <Field label="Mulai" hint="jam:menit:detik">
            {(p) => <input {...p} className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />}
          </Field>
          <Field label="Selesai" hint={`Maks. ${formatClock(est.duration_ms)}`}>
            {(p) => <input {...p} className={inputClass} value={endText} onChange={(e) => setEnd(e.target.value)} />}
          </Field>
        </div>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}

      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Tahan dulu</Button>
        <Button variant="primary" disabled={busy} onClick={submit}>
          {busy ? "Melanjutkan…" : "Lanjutkan"}
        </Button>
      </div>
    </div>
  );
}
