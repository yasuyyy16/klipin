import type { ReactNode } from "react";

/** Halaman yang belum dibangun: judul + label jujur, tanpa kontrol palsu (R-26). */
export function PagePlaceholder({ title, purpose, note = "Halaman ini belum tersedia di versi ini." }: {
  title: string;
  purpose: string;
  note?: ReactNode;
}) {
  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-3xl px-6 py-10">
      <h1 id="page-title" className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-muted">{purpose}</p>
      <p className="mt-6 rounded-card border border-dashed border-border px-4 py-3 text-muted">{note}</p>
    </section>
  );
}
