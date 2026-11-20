import { useEffect, useState } from "react";
import { Modal } from "./Modal";

/** Daftar pintasan 08-ui-ux.md §6; `?` membukanya dari halaman mana pun. */
const SHORTCUTS: [string, string, string][] = [
  ["Spasi", "Putar/jeda", "Monitor Live, Review, Editor"],
  ["J / K", "Klip berikutnya / sebelumnya", "Review Klip"],
  ["A", "Setujui", "Review, Editor"],
  ["X", "Tolak", "Review Klip"],
  ["E", "Buka editor", "Review Klip"],
  ["R", "Render", "Review, Editor"],
  ["U", "Buka Dialog Unggah", "Review Klip (klip dirender)"],
  ["[ / ]", "Set awal/akhir trim di playhead", "Editor Klip"],
  ["← / →", "Geser playhead 1 detik (Shift = 0,1 detik)", "Review, Editor"],
  ["M", "Klip N detik terakhir", "Monitor Live"],
  ["?", "Tampilkan daftar pintasan", "Semua"],
];

export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function ShortcutsDialog() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const question = e.key === "?" || (e.key === "/" && e.shiftKey);
      if (question && !isTyping(e.target)) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <Modal open={open} onClose={() => setOpen(false)} title="Pintasan keyboard">
      <table className="w-full text-left">
        <caption className="sr-only">Pintasan keyboard Klipin</caption>
        <thead className="text-xs text-muted">
          <tr>
            <th scope="col" className="pb-2 font-medium">Tombol</th>
            <th scope="col" className="pb-2 font-medium">Aksi</th>
            <th scope="col" className="pb-2 font-medium">Halaman</th>
          </tr>
        </thead>
        <tbody>
          {SHORTCUTS.map(([key, action, page]) => (
            <tr key={key} className="border-t border-border">
              <td className="py-2 pr-3">
                <kbd className="rounded-input bg-surface-2 px-1.5 py-0.5 font-mono text-xs">{key}</kbd>
              </td>
              <td className="py-2 pr-3">{action}</td>
              <td className="py-2 text-muted">{page}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-4 text-xs text-muted">Pintasan tidak aktif saat mengetik di kolom teks.</p>
    </Modal>
  );
}
