import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { JOB_TYPE_LABEL, useActiveJobs } from "../api/jobs";
import { updateYtdlp } from "../api/settings";
import {
  importVod, inspectStream, PLATFORM_LABEL, STREAM_STATUS, useStreams, type InspectResult,
} from "../api/streams";
import { Button } from "../components/Button";
import { inputClass } from "../components/Field";
import { useToast } from "../components/Toast";
import { formatBytes, formatClock } from "../format";
import { navigate } from "../router";

const DEBOUNCE_MS = 500;
const DISK_FACTOR = 1.5; // FR-001
const BANNER_KEY = "klipin.banner-izin-ditutup";

type InspectState =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "error"; error: ApiError }
  | { kind: "ok"; url: string; info: InspectResult };

function toApiError(err: unknown) {
  return err instanceof ApiError
    ? err
    : new ApiError(500, "INTERNAL_ERROR", "Terjadi kesalahan di Klipin. Detail ada di log.");
}

function readBannerClosed() {
  try {
    return window.localStorage.getItem(BANNER_KEY) === "1";
  } catch {
    return false;
  }
}

function PermissionBanner() {
  const [closed, setClosed] = useState(readBannerClosed);
  if (closed) return null;
  return (
    <div className="flex items-center justify-between gap-3 rounded-card border border-warning/40 bg-warning/10 px-4 py-2">
      <p>Pastikan kamu punya izin untuk mengklip stream ini.</p>
      <Button
        aria-label="Tutup pengingat izin"
        onClick={() => {
          setClosed(true);
          try {
            window.localStorage.setItem(BANNER_KEY, "1");
          } catch {
            /* penyimpanan browser tidak tersedia: cukup tutup untuk sesi ini */
          }
        }}
      >
        Tutup
      </Button>
    </div>
  );
}

/** Kebutuhan ruang disk (FR-001); null bila ukuran tidak diketahui atau ruang cukup. */
function diskShortage(info: InspectResult) {
  if (info.estimated_size_bytes == null) return null;
  const required = Math.round(info.estimated_size_bytes * DISK_FACTOR);
  if (info.disk_free_bytes >= required) return null;
  return `Butuh ±${formatBytes(required)}, tersedia ${formatBytes(info.disk_free_bytes)}. `
    + "Kosongkan ruang atau hapus video sumber lama.";
}

function UpdateYtdlpButton() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          toast((await updateYtdlp()).message, "success");
        } catch (err) {
          toast(toApiError(err).message, "error");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Memperbarui yt-dlp…" : "Perbarui yt-dlp"}
    </Button>
  );
}

function MetadataCard({ url, info }: { url: string; info: InspectResult }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const shortage = diskShortage(info);

  const onImport = async () => {
    setBusy(true);
    setError(null);
    try {
      const { stream } = await importVod(url);
      qc.invalidateQueries({ queryKey: ["streams"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast("Impor dimulai. Video sedang diunduh.", "success");
      navigate(`/streams/${stream.id}`);
    } catch (err) {
      setError(toApiError(err));
      setBusy(false);
    }
  };

  const facts = [
    { label: "Durasi", value: info.is_live ? "Sedang live" : formatClock(info.duration_ms) },
    { label: "Chat replay", value: info.has_chat_replay ? "Tersedia" : "Tidak ada" },
    {
      label: "Perkiraan ukuran",
      value: info.estimated_size_bytes == null
        ? "Tidak diketahui"
        : `±${formatBytes(info.estimated_size_bytes)}`,
    },
    { label: "Ruang kosong", value: formatBytes(info.disk_free_bytes) },
  ];
  const existingId = error?.fields.existing_stream_id;

  return (
    <article aria-labelledby="inspect-title" className="space-y-4 rounded-card border border-border bg-surface p-4">
      <div className="space-y-1">
        <p className="text-muted">
          {PLATFORM_LABEL[info.platform]}
          {info.is_live && <span className="ml-2 font-medium text-live">● LIVE</span>}
        </p>
        <h2 id="inspect-title" className="text-xl font-semibold">{info.title}</h2>
        <p className="flex flex-wrap items-center gap-2 text-muted">
          {info.channel.name ?? "Kanal tidak diketahui"}
          {info.channel.known_channel_id != null && (
            <span className="rounded-input border border-border px-2 py-0.5 text-xs text-text">Kanal dikenal</span>
          )}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {facts.map((f) => (
          <div key={f.label}>
            <dt className="text-xs text-muted">{f.label}</dt>
            <dd className="font-medium">{f.value}</dd>
          </div>
        ))}
      </dl>

      {info.is_live ? (
        <p role="status" className="rounded-input border border-live/40 bg-live/10 px-3 py-2">
          Stream ini masih live. Rekam live belum tersedia di versi ini; impor VOD-nya setelah siaran selesai.
        </p>
      ) : (
        <div className="space-y-2">
          {shortage && <p role="alert" className="text-danger">{shortage}</p>}
          <Button variant="primary" disabled={busy || shortage !== null} onClick={onImport}>
            {busy ? "Membuat Stream Sumber…" : "Impor VOD"}
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-danger">
          {error.message}
          {existingId && (
            <> <a href={`#/streams/${existingId}`} className="text-text underline">Buka stream itu</a></>
          )}
        </p>
      )}
    </article>
  );
}

function InspectSkeleton() {
  return (
    <div role="status" className="space-y-3 rounded-card border border-border bg-surface p-4">
      <p className="text-muted">Membaca info video…</p>
      <div aria-hidden="true" className="h-6 w-2/3 animate-pulse rounded-input bg-surface-2" />
      <div aria-hidden="true" className="h-4 w-1/3 animate-pulse rounded-input bg-surface-2" />
      <div aria-hidden="true" className="h-10 w-full animate-pulse rounded-input bg-surface-2" />
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="rounded-card border border-dashed border-border px-4 py-3 text-muted">
      <p>Contoh link yang bisa dipakai:</p>
      <ul className="mt-1 list-inside list-disc font-mono text-xs">
        <li>https://www.youtube.com/watch?v=…</li>
        <li>https://youtu.be/…</li>
        <li>https://kick.com/namakanal/videos/…</li>
      </ul>
    </div>
  );
}

function RecentStreams() {
  const { data, isLoading, isError } = useStreams(5);
  const { data: active } = useActiveJobs();
  const runningFor = (streamId: number) =>
    active?.items.find((j) => j.source_stream_id === streamId && j.status === "running");

  return (
    <section aria-labelledby="recent-title" className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 id="recent-title" className="text-base font-semibold">Stream terakhir</h2>
        <a href="#/streams" className="text-muted hover:text-text hover:underline">Lihat semua</a>
      </div>
      {isLoading && <p className="text-muted">Memuat…</p>}
      {isError && <p className="text-danger">Daftar stream tidak bisa dimuat.</p>}
      {data && data.items.length === 0 && (
        <p className="text-muted">Belum ada stream. Tempel link di atas untuk mulai.</p>
      )}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {data.items.map((s) => {
            const status = STREAM_STATUS[s.status];
            const job = runningFor(s.id);
            return (
              <li key={s.id}>
                <a href={`#/streams/${s.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{s.title}</span>
                    <span className="text-xs text-muted">
                      {[s.channel?.name, PLATFORM_LABEL[s.platform], formatClock(s.duration_ms)]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  {job && (
                    <span className="flex items-center gap-2 text-xs text-muted">
                      {JOB_TYPE_LABEL[job.job_type] ?? job.job_type} {job.progress_pct}%
                      <span aria-hidden="true" className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                        <span className="block h-full bg-primary" style={{ width: `${job.progress_pct}%` }} />
                      </span>
                    </span>
                  )}
                  <span className={`whitespace-nowrap ${status.className}`}>
                    <span aria-hidden="true">{status.symbol} </span>{status.label}
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function P01Beranda() {
  const [url, setUrl] = useState("");
  const [state, setState] = useState<InspectState>({ kind: "empty" });
  const latest = useRef(0);

  const runInspect = async (value: string) => {
    const trimmed = value.trim();
    const seq = ++latest.current;
    if (!trimmed) {
      setState({ kind: "empty" });
      return;
    }
    setState({ kind: "loading" });
    try {
      const info = await inspectStream(trimmed);
      if (seq === latest.current) setState({ kind: "ok", url: trimmed, info });
    } catch (err) {
      if (seq === latest.current) setState({ kind: "error", error: toApiError(err) });
    }
  };

  // Inspect otomatis 500 ms setelah berhenti mengetik/menempel (08-ui-ux.md P-01).
  useEffect(() => {
    const id = window.setTimeout(() => runInspect(url), DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [url]);

  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <h1 id="page-title" className="text-2xl font-semibold">Beranda</h1>
      <PermissionBanner />

      <form
        className="space-y-1"
        onSubmit={(e) => {
          e.preventDefault();
          runInspect(url);
        }}
      >
        <label htmlFor="stream-url" className="block font-medium">Tempel link VOD atau live YouTube/Kick</label>
        <input
          id="stream-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://www.youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className={`${inputClass} min-h-11 text-base`}
        />
      </form>

      {state.kind === "empty" && <EmptyHint />}
      {state.kind === "loading" && <InspectSkeleton />}
      {state.kind === "error" && (
        <div role="alert" className="space-y-2 rounded-card border border-danger/40 bg-danger/10 px-4 py-3">
          <p>{state.error.message}</p>
          {state.error.code === "UPSTREAM_ERROR" && <UpdateYtdlpButton />}
        </div>
      )}
      {state.kind === "ok" && <MetadataCard key={state.url} url={state.url} info={state.info} />}

      <RecentStreams />
    </section>
  );
}
