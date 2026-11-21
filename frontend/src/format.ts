/** Format angka untuk teks UI (Bahasa Indonesia). */

/** Durasi media: 3:00:45 atau 4:05. */
export function formatClock(ms: number | null): string {
  if (ms == null) return "–";
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Ukuran file desimal (1 GB = 10⁹ byte, sama dengan pesan ruang disk di server): "9,6 GB". */
export function formatBytes(n: number | null): string {
  if (n == null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i++;
  }
  const digits = i >= 2 ? 1 : 0;
  return `${v.toLocaleString("id-ID", { maximumFractionDigits: digits, minimumFractionDigits: digits })} ${units[i]}`;
}
