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

/** Durasi dalam kata (sama dengan server): "2 jam 10 menit", "45 menit", "30 detik". */
export function formatDurationWords(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (!h && !m) return `${total} detik`;
  return [h ? `${h} jam` : "", m ? `${m} menit` : ""].filter(Boolean).join(" ");
}

/** "1:02:03", "62:03", atau "62" (menit) → milidetik; null bila tidak valid. */
export function parseClock(text: string): number | null {
  const parts = text.trim().split(":");
  if (!parts[0] || parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return null;
  const nums = parts.map(Number);
  if (nums.length === 1) return nums[0] * 60_000;
  if (nums.slice(1).some((n) => n >= 60)) return null;
  const [h, m, s] = nums.length === 3 ? nums : [0, nums[0], nums[1]];
  return ((h * 60 + m) * 60 + s) * 1000;
}
