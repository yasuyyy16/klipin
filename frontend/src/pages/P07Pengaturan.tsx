import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import {
  deleteSecret, saveSecret, saveSettings, settingsKey, testSecret, updateYtdlp, useHealth, useSettings,
  type SecretName, type SecretTest, type Settings,
} from "../api/settings";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Field, inputClass } from "../components/Field";
import { useToast } from "../components/Toast";
import { useLocation } from "../router";

const TABS = [
  { id: "umum", label: "Umum" },
  { id: "api", label: "API & Penyedia" },
  { id: "skor", label: "Skor Highlight" },
  { id: "sistem", label: "Sistem" },
] as const;

type Errors = Record<string, string>;

function useSave() {
  const qc = useQueryClient();
  const toast = useToast();
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  async function save(changes: Partial<Settings>) {
    setSaving(true);
    setErrors({});
    try {
      qc.setQueryData(settingsKey, await saveSettings(changes));
      toast("Pengaturan tersimpan.", "success");
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fields);
        toast(err.message, "error");
      } else toast("Pengaturan gagal disimpan.", "error");
    } finally {
      setSaving(false);
    }
  }
  return { save, errors, saving };
}

function SaveBar({ saving }: { saving: boolean }) {
  return (
    <div className="flex justify-end border-t border-border pt-4">
      <Button type="submit" variant="primary" disabled={saving}>{saving ? "Menyimpan…" : "Simpan"}</Button>
    </div>
  );
}

function TabUmum({ s }: { s: Settings }) {
  const { save, errors, saving } = useSave();
  const initial = {
    output_dir: s.output_dir,
    max_heavy_jobs: s.max_heavy_jobs,
    live_last_n_default_s: s.live_last_n_default_s,
    live_segment_seconds: s.live_segment_seconds,
    live_block_minutes: s.live_block_minutes,
  };
  const [form, setForm] = useState(initial);
  const set = (k: keyof typeof form) => (v: string) =>
    setForm((f) => ({ ...f, [k]: k === "output_dir" ? v : Number(v) }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Kirim hanya yang diubah: output_dir tampil sebagai path absolut, tetapi nilai
    // tersimpannya bisa relatif terhadap folder kerja dan tidak boleh ikut berubah.
    const changes = Object.fromEntries(
      Object.entries(form).filter(([k, v]) => v !== initial[k as keyof typeof initial]),
    );
    save(changes);
  };
  return (
    <form onSubmit={submit} className="space-y-5">
      <Field label="Folder output" hint="Tempat MP4 & .srt hasil render disimpan." error={errors.output_dir}>
        {(p) => <input {...p} className={inputClass} value={form.output_dir} onChange={(e) => set("output_dir")(e.target.value)} />}
      </Field>
      <Field label="Mode unggah default" hint="Unggah otomatis ke platform tersedia di versi berikutnya.">
        {(p) => (
          <select {...p} className={inputClass} value="manual" disabled>
            <option value="manual">Manual (Paket Unggah)</option>
          </select>
        )}
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Job berat paralel" hint="Unduh, transkripsi, dan render yang boleh jalan bersamaan." error={errors.max_heavy_jobs}>
          {(p) => <input {...p} type="number" min={1} className={inputClass} value={form.max_heavy_jobs} onChange={(e) => set("max_heavy_jobs")(e.target.value)} />}
        </Field>
        <Field label='Durasi default "Klip N detik terakhir"' error={errors.live_last_n_default_s}>
          {(p) => (
            <select {...p} className={inputClass} value={form.live_last_n_default_s} onChange={(e) => set("live_last_n_default_s")(e.target.value)}>
              {[15, 30, 60, 90].map((n) => <option key={n} value={n}>{n} detik</option>)}
            </select>
          )}
        </Field>
        <Field label="Ukuran segmen live (detik)" error={errors.live_segment_seconds}>
          {(p) => <input {...p} type="number" min={1} className={inputClass} value={form.live_segment_seconds} onChange={(e) => set("live_segment_seconds")(e.target.value)} />}
        </Field>
        <Field label="Ukuran blok analisis live (menit)" error={errors.live_block_minutes}>
          {(p) => <input {...p} type="number" min={1} className={inputClass} value={form.live_block_minutes} onChange={(e) => set("live_block_minutes")(e.target.value)} />}
        </Field>
      </div>
      <SaveBar saving={saving} />
    </form>
  );
}

const SECRET_LABEL: Record<SecretName, string> = {
  transcriber_api_key: "API key transkripsi",
  llm_api_key: "API key LLM",
};

function SecretCard({ name, state }: { name: SecretName; state: Settings["secrets"][SecretName] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SecretTest | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function act(fn: () => Promise<unknown>, success?: string) {
    setBusy(true);
    setError(undefined);
    try {
      await fn();
      if (success) toast(success, "success");
      await qc.invalidateQueries({ queryKey: settingsKey });
    } catch (err) {
      const msg = err instanceof ApiError ? Object.values(err.fields)[0] ?? err.message : "Gagal menyimpan API key.";
      setError(msg);
      toast(err instanceof ApiError ? err.message : msg, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-card border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">{SECRET_LABEL[name]}</h3>
        <span className={state.set ? "text-text" : "text-muted"}>
          {state.set ? <>Tersimpan <span className="font-mono">{state.masked}</span></> : "Belum diisi"}
        </span>
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            await saveSecret(name, value);
            setValue("");
            setResult(null);
          }, "API key tersimpan.");
        }}
      >
        <div className="min-w-60 flex-1">
          <Field label={state.set ? "Ganti API key" : "Isi API key"} error={error}>
            {(p) => (
              <input {...p} type="password" autoComplete="off" spellCheck={false} className={inputClass}
                value={value} onChange={(e) => setValue(e.target.value)} />
            )}
          </Field>
        </div>
        <Button type="submit" variant="primary" disabled={busy || !value.trim()}>Simpan</Button>
        <Button
          disabled={busy || !state.set}
          onClick={() => act(async () => setResult(await testSecret(name)))}
        >
          {busy ? "Memproses…" : "Tes koneksi"}
        </Button>
        <Button variant="danger" disabled={busy || !state.set} onClick={() => setConfirmDelete(true)}>Hapus</Button>
      </form>
      {result && (
        <p role="status" className={result.ok ? "text-success" : "text-danger"}>
          {result.ok
            ? `✓ Terhubung ke ${result.provider}${result.latency_ms !== null ? ` (${result.latency_ms} ms)` : ""}.`
            : `✕ Gagal: ${result.error}`}
        </p>
      )}
      <ConfirmDialog
        open={confirmDelete}
        title={`Hapus ${SECRET_LABEL[name]}?`}
        message="Job yang butuh API key ini akan gagal sampai kamu mengisinya lagi."
        confirmLabel="Hapus API key"
        danger
        busy={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          await act(() => deleteSecret(name), "API key dihapus.");
          setResult(null);
          setConfirmDelete(false);
        }}
      />
    </div>
  );
}

function TabApi({ s }: { s: Settings }) {
  const { save, errors, saving } = useSave();
  const [form, setForm] = useState({
    transcriber_provider: s.transcriber_provider,
    llm_provider: s.llm_provider,
    llm_models: s.llm_models,
    confirm_usage_over_min: s.confirm_usage_over_min,
    max_audio_minutes_per_job: s.max_audio_minutes_per_job,
  });
  const [lastThreshold, setLastThreshold] = useState(s.confirm_usage_over_min ?? 30);
  const setModel = (k: keyof Settings["llm_models"], v: string) =>
    setForm((f) => ({ ...f, llm_models: { ...f.llm_models, [k]: v.trim() ? v.trim() : null } }));
  return (
    <div className="space-y-6">
      {!s.storage.keyring_available && (
        <p role="alert" className="rounded-card border border-warning/50 bg-warning/10 px-4 py-3">
          Keyring OS tidak tersedia. API key disimpan di file <code className="font-mono">.env</code> lokal sebagai teks biasa.
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <SecretCard name="transcriber_api_key" state={s.secrets.transcriber_api_key} />
        <SecretCard name="llm_api_key" state={s.secrets.llm_api_key} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); save(form); }} className="space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Penyedia transkripsi" error={errors.transcriber_provider}>
            {(p) => (
              <select {...p} className={inputClass} value={form.transcriber_provider}
                onChange={(e) => setForm((f) => ({ ...f, transcriber_provider: e.target.value as Settings["transcriber_provider"] }))}>
                <option value="deepgram">Deepgram</option>
                <option value="assemblyai">AssemblyAI</option>
              </select>
            )}
          </Field>
          <Field label="Penyedia LLM">
            {(p) => (
              <select {...p} className={inputClass} value={form.llm_provider} disabled>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            )}
          </Field>
        </div>
        <fieldset className="space-y-3">
          <legend className="font-medium">Model LLM per tugas</legend>
          <p className="text-xs text-muted">Isi nama model dari konsol penyedia. Kosongkan jika belum dipilih.</p>
          <div className="grid gap-5 sm:grid-cols-3">
            {([
              ["judge_highlight", "Menilai highlight"],
              ["translate_lines", "Menerjemahkan subtitle"],
              ["write_captions", "Menulis caption"],
            ] as const).map(([k, label]) => (
              <Field key={k} label={label} error={errors[`llm_models.${k}`]}>
                {(p) => <input {...p} className={inputClass} value={form.llm_models[k] ?? ""} onChange={(e) => setModel(k, e.target.value)} />}
              </Field>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="flex items-center gap-2 font-medium">
              <input type="checkbox" checked={form.confirm_usage_over_min !== null}
                onChange={(e) => setForm((f) => ({ ...f, confirm_usage_over_min: e.target.checked ? lastThreshold : null }))} />
              Minta konfirmasi sebelum transkripsi
            </label>
            <Field label="Untuk stream lebih dari (menit)" hint="0 = selalu minta konfirmasi." error={errors.confirm_usage_over_min}>
              {(p) => <input {...p} type="number" min={0} className={inputClass} disabled={form.confirm_usage_over_min === null}
                value={form.confirm_usage_over_min ?? lastThreshold}
                onChange={(e) => {
                  setLastThreshold(Number(e.target.value));
                  setForm((f) => ({ ...f, confirm_usage_over_min: Number(e.target.value) }));
                }} />}
            </Field>
          </div>
          <Field label="Batas durasi audio per Job (menit)" error={errors.max_audio_minutes_per_job}>
            {(p) => <input {...p} type="number" min={1} className={inputClass} value={form.max_audio_minutes_per_job}
              onChange={(e) => setForm((f) => ({ ...f, max_audio_minutes_per_job: Number(e.target.value) }))} />}
          </Field>
        </div>
        <p className="text-xs text-muted">
          Batas durasi tetap berlaku walau konfirmasi dimatikan. Klipin tidak menampilkan harga;{" "}
          cek halaman harga:{" "}
          {[["Deepgram", "deepgram"], ["AssemblyAI", "assemblyai"], ["Anthropic", "anthropic"]].map(([label, k], i) => (
            <span key={k}>
              {i > 0 && " · "}
              <a href={s.pricing_links[k]} target="_blank" rel="noreferrer" className="text-text underline">{label}</a>
            </span>
          ))}
        </p>
        <SaveBar saving={saving} />
      </form>
    </div>
  );
}

const WEIGHT_LABEL = { audio: "Audio", chat: "Chat", llm: "LLM" } as const;

function TabSkor({ s }: { s: Settings }) {
  // Pesan bobot tidak diambil dari error server: keterangan total di bawah slider sudah
  // menampilkannya dan selalu sesuai nilai terkini.
  const { save, errors, saving } = useSave();
  const [weights, setWeights] = useState({
    audio: Math.round(s.score_weights.audio * 100),
    chat: Math.round(s.score_weights.chat * 100),
    llm: Math.round(s.score_weights.llm * 100),
  });
  const [threshold, setThreshold] = useState(s.score_min_threshold);
  const [delayS, setDelayS] = useState(s.chat_delay_ms / 1000);
  const [words, setWords] = useState(s.chat_reaction_words);
  const [newWord, setNewWord] = useState("");
  const [kick, setKick] = useState(s.kick_live_chat_enabled);
  const total = weights.audio + weights.chat + weights.llm;

  const addWord = () => {
    const w = newWord.trim();
    if (w && !words.includes(w)) setWords([...words, w]);
    setNewWord("");
  };

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        save({
          score_weights: { audio: weights.audio / 100, chat: weights.chat / 100, llm: weights.llm / 100 },
          score_min_threshold: threshold,
          chat_delay_ms: Math.round(delayS * 1000),
          chat_reaction_words: words,
          kick_live_chat_enabled: kick,
        });
      }}
    >
      <fieldset className="space-y-4">
        <legend className="font-medium">Bobot Sinyal</legend>
        {(Object.keys(WEIGHT_LABEL) as (keyof typeof WEIGHT_LABEL)[]).map((k) => (
          <div key={k} className="grid grid-cols-[6rem_1fr_5rem] items-center gap-3">
            <label htmlFor={`w-${k}`}>{WEIGHT_LABEL[k]}</label>
            <input id={`w-${k}`} type="range" min={0} max={100} value={weights[k]}
              onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
              className="accent-primary" />
            <span className="text-right tabular-nums">{weights[k]}%</span>
          </div>
        ))}
        <p className={total === 100 ? "text-muted" : "text-danger"} aria-live="polite">
          Total {total}%{total === 100 ? "" : ". Total bobot harus 100%."}
        </p>
      </fieldset>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Ambang skor minimum" hint="Kandidat dengan skor di bawah ini tidak dibuat (0–100)." error={errors.score_min_threshold}>
          {(p) => <input {...p} type="number" min={0} max={100} className={inputClass} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />}
        </Field>
        <Field label="Jeda Chat (detik)" hint="Chat biasanya bereaksi beberapa detik setelah momen (0–30)." error={errors.chat_delay_ms}>
          {(p) => <input {...p} type="number" min={0} max={30} step={0.5} className={inputClass} value={delayS} onChange={(e) => setDelayS(Number(e.target.value))} />}
        </Field>
      </div>
      <fieldset className="space-y-2">
        <legend className="font-medium">Kata reaksi chat</legend>
        <ul className="flex flex-wrap gap-2" aria-label="Kata reaksi">
          {words.map((w) => (
            <li key={w} className="flex items-center gap-1 rounded-full bg-surface-2 py-0.5 pr-1 pl-3">
              {w}
              <button type="button" aria-label={`Hapus kata ${w}`} onClick={() => setWords(words.filter((x) => x !== w))}
                className="flex h-6 w-6 items-center justify-center rounded-full text-muted hover:bg-border hover:text-text">
                <span aria-hidden="true">✕</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="flex max-w-sm gap-2">
          <label htmlFor="new-word" className="sr-only">Kata reaksi baru</label>
          <input id="new-word" className={inputClass} placeholder="mis. wkwk" value={newWord}
            onChange={(e) => setNewWord(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addWord(); } }} />
          <Button onClick={addWord} disabled={!newWord.trim()}>Tambah</Button>
        </div>
        {errors.chat_reaction_words && <p className="text-xs text-danger">{errors.chat_reaction_words}</p>}
      </fieldset>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={kick} onChange={(e) => setKick(e.target.checked)} className="h-4 w-4 accent-primary" />
        Ambil chat live Kick (eksperimental)
      </label>
      <SaveBar saving={saving} />
    </form>
  );
}

function TabSistem() {
  const { data, isLoading, isError, refetch, isFetching } = useHealth();
  const toast = useToast();
  const [updating, setUpdating] = useState(false);
  const [updateMsg, setUpdateMsg] = useState<string | null>(null);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => refetch()} disabled={isFetching}>{isFetching ? "Memeriksa…" : "Periksa ulang"}</Button>
        <Button
          disabled={updating}
          onClick={async () => {
            setUpdating(true);
            try {
              const r = await updateYtdlp();
              setUpdateMsg(r.message);
              toast(r.message, "success");
              refetch();
            } catch (err) {
              const msg = err instanceof ApiError ? err.message : "Gagal memperbarui yt-dlp.";
              setUpdateMsg(msg);
              toast(msg, "error");
            } finally {
              setUpdating(false);
            }
          }}
        >
          {updating ? "Memperbarui yt-dlp…" : "Perbarui yt-dlp"}
        </Button>
        {updateMsg && <p role="status" className="text-muted">{updateMsg}</p>}
      </div>
      {isLoading && <p className="text-muted">Memeriksa FFmpeg, yt-dlp, SQLite, keyring, dan ruang disk…</p>}
      {isError && <p className="text-danger">Pemeriksaan sistem gagal dimuat. Coba "Periksa ulang".</p>}
      {data && (
        <>
          <table className="w-full text-left">
            <caption className="sr-only">Hasil pemeriksaan sistem</caption>
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="pb-2 font-medium">Komponen</th>
                <th scope="col" className="pb-2 font-medium">Status</th>
                <th scope="col" className="pb-2 font-medium">Keterangan</th>
              </tr>
            </thead>
            <tbody>
              {data.checks.map((c) => (
                <tr key={c.name} className="border-t border-border">
                  <td className="py-2 pr-3">{c.name}</td>
                  <td className={`py-2 pr-3 whitespace-nowrap ${c.ok ? "text-success" : "text-danger"}`}>
                    <span aria-hidden="true">{c.ok ? "✓ " : "✕ "}</span>{c.ok ? "OK" : "Bermasalah"}
                  </td>
                  <td className="py-2 text-muted">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="grid gap-x-6 gap-y-1 text-muted sm:grid-cols-[auto_1fr]">
            <dt>Folder kerja</dt><dd className="font-mono text-xs break-all">{data.home}</dd>
            <dt>Lokasi backup</dt><dd className="font-mono text-xs break-all">{data.backup_dir}</dd>
          </dl>
        </>
      )}
    </div>
  );
}

export default function P07Pengaturan() {
  const { query } = useLocation();
  const tab = TABS.find((t) => t.id === query.get("tab"))?.id ?? "umum";
  const { data, isLoading, isError, refetch } = useSettings();

  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-4xl px-6 py-8">
      <h1 id="page-title" className="text-2xl font-semibold">Pengaturan</h1>
      <nav aria-label="Bagian pengaturan" className="mt-6 flex flex-wrap gap-1 border-b border-border">
        {TABS.map((t) => (
          <a key={t.id} href={`#/settings?tab=${t.id}`} aria-current={tab === t.id ? "page" : undefined}
            className={`-mb-px flex min-h-10 items-center border-b-2 px-3 whitespace-nowrap ${tab === t.id
              ? "border-primary text-text" : "border-transparent text-muted hover:text-text"}`}>
            {t.label}
          </a>
        ))}
      </nav>
      <div className="mt-6">
        {tab === "sistem" ? <TabSistem /> : (
          <>
            {isLoading && <p className="text-muted">Memuat pengaturan…</p>}
            {isError && (
              <div className="flex items-center gap-3">
                <p className="text-danger">Pengaturan tidak bisa dimuat. Pastikan Klipin masih berjalan.</p>
                <Button onClick={() => refetch()}>Muat ulang</Button>
              </div>
            )}
            {data && tab === "umum" && <TabUmum s={data} />}
            {data && tab === "api" && <TabApi s={data} />}
            {data && tab === "skor" && <TabSkor s={data} />}
          </>
        )}
      </div>
    </section>
  );
}
