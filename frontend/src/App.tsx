import type { ComponentType } from "react";
import { useServerEvents } from "./api/events";
import { Header } from "./components/Header";
import { ShortcutsDialog } from "./components/Shortcuts";
import { PagePlaceholder } from "./components/PagePlaceholder";
import { match, useLocation } from "./router";
import P01Beranda from "./pages/P01Beranda";
import P02DaftarStream from "./pages/P02DaftarStream";
import P03MonitorLive from "./pages/P03MonitorLive";
import P04ReviewKlip from "./pages/P04ReviewKlip";
import P05EditorKlip from "./pages/P05EditorKlip";
import P06AntreanJob from "./pages/P06AntreanJob";
import P07Pengaturan from "./pages/P07Pengaturan";

// Rute 08-ui-ux.md §2; urutan penting (pola spesifik dulu).
const ROUTES: [string, ComponentType<{ params: Record<string, string> }>][] = [
  ["/", P01Beranda],
  ["/streams", P02DaftarStream],
  ["/streams/:id/live", P03MonitorLive],
  ["/streams/:id", P04ReviewKlip],
  ["/clips/:id/edit", P05EditorKlip],
  ["/jobs", P06AntreanJob],
  ["/settings", P07Pengaturan],
];

function Routes() {
  const { path } = useLocation();
  for (const [pattern, Page] of ROUTES) {
    const params = match(pattern, path);
    if (params) return <Page params={params} />;
  }
  return (
    <PagePlaceholder
      title="Halaman tidak ditemukan"
      purpose={`Tidak ada halaman di alamat ${path}.`}
      note={<a href="#/" className="text-text underline">Kembali ke Beranda</a>}
    />
  );
}

export default function App() {
  useServerEvents();
  return (
    <>
      {/* Tombol, bukan <a href="#main">, karena hash dipakai router. */}
      <button
        type="button"
        onClick={() => document.getElementById("main")?.focus()}
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-input focus:bg-surface-2 focus:px-3 focus:py-2"
      >
        Langsung ke konten
      </button>
      <Header />
      <main id="main" tabIndex={-1} className="outline-none">
        <Routes />
      </main>
      <ShortcutsDialog />
    </>
  );
}
