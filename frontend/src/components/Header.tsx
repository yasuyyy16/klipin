import { useActiveJobs, JOB_TYPE_LABEL } from "../api/jobs";
import { useLocation } from "../router";

const NAV = [
  { href: "#/", label: "Beranda", active: (p: string) => p === "/" },
  { href: "#/streams", label: "Stream", active: (p: string) => p.startsWith("/streams") || p.startsWith("/clips") },
  { href: "#/jobs", label: "Antrean Job", active: (p: string) => p === "/jobs" },
  { href: "#/settings", label: "Pengaturan", active: (p: string) => p === "/settings" },
];

/** Indikator Job aktif: jumlah + progres Job berjalan; klik menuju P-06. */
function JobIndicator() {
  const { data, isError } = useActiveJobs();
  if (isError) {
    return <a href="#/jobs" className="text-danger hover:underline">Status Job tidak terbaca</a>;
  }
  const items = data?.items ?? [];
  const running = items.find((j) => j.status === "running");
  const label = items.length === 0
    ? "Tidak ada Job berjalan"
    : running
      ? `${JOB_TYPE_LABEL[running.job_type] ?? running.job_type} ${running.progress_pct}%` +
        (items.length > 1 ? ` · ${items.length - 1} lainnya` : "")
      : `${items.length} Job menunggu`;
  return (
    <a
      href="#/jobs"
      className="flex min-h-8 items-center gap-2 rounded-input px-3 whitespace-nowrap text-muted hover:bg-surface-2 hover:text-text"
      aria-label={`Antrean Job: ${label}`}
    >
      {running && (
        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
          <span className="block h-full bg-primary transition-[width]" style={{ width: `${running.progress_pct}%` }} />
        </span>
      )}
      <span aria-hidden="true">{label}</span>
    </a>
  );
}

export function Header() {
  const { path } = useLocation();
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg">
      <div className="flex min-h-14 flex-wrap items-center gap-x-6 gap-y-2 px-6 py-2">
        <a href="#/" className="text-base font-semibold tracking-tight">Klipin</a>
        <nav aria-label="Navigasi utama" className="flex flex-wrap gap-1">
          {NAV.map((n) => {
            const active = n.active(path);
            return (
              <a
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-8 items-center rounded-input px-3 whitespace-nowrap ${
                  active ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text"
                }`}
              >
                {n.label}
              </a>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <JobIndicator />
        </div>
      </div>
      <p className="border-t border-border px-6 py-2 text-xs text-muted lg:hidden">
        Klipin dirancang untuk layar minimal 1024 px. Di layar ini tampilan menjadi satu kolom.
      </p>
    </header>
  );
}
