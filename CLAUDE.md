# CLAUDE.md: Klipin

## Tentang proyek
Klipin adalah aplikasi web **lokal** (FastAPI + React, dibuka di `http://127.0.0.1:8765`) untuk satu pengguna. Aplikasi ini mengubah livestream YouTube/Kick (VOD atau live) menjadi klip vertikal 9:16. Prosesnya: transkripsi, deteksi posisi cam untuk menyusun layout (gaming, podcast, IRL, dll.), ranking momen highlight dari sinyal audio + chat + LLM, subtitle otomatis (Indonesia/Inggris + terjemahan), render MP4 + .srt, lalu unggah **manual** (Paket Unggah) atau, mulai v1.1, **otomatis** ke YouTube/TikTok/Instagram/Facebook.

## Dokumen acuan (sumber kebenaran)
Semua spesifikasi ada di `docs/spec/`. Baca dokumen yang relevan **sebelum** mengerjakan task.
| Kebutuhan | Dokumen |
|---|---|
| Lingkup, fitur F-xx, istilah | `docs/spec/01-prd.md` (Kamus Istilah §8) |
| Perilaku, kriteria penerimaan, BR, NFR | `docs/spec/02-requirements.md` |
| Alur & state machine (Stream Sumber, Job, Klip, Unggahan) | `docs/spec/03-user-flow.md` §4 |
| Komponen, pipeline Job, ADR, struktur folder, env, instalasi | `docs/spec/04-arsitektur.md` |
| Skema SQLite (DDL lengkap, enum, seed, JSON) | `docs/spec/05-database.md` |
| Endpoint, format error, token sesi, SSE | `docs/spec/06-api.md` |
| yt-dlp, transkripsi, LLM, OAuth & unggah per platform | `docs/spec/07-integrasi.md` |
| Halaman P-xx, komponen, pintasan, teks UI | `docs/spec/08-ui-ux.md` |
| Kasus uji TC-xxx, fixture, kriteria rilis | `docs/spec/09-testing.md` |
| Fase & urutan | `docs/spec/10-roadmap.md` |
| Daftar pekerjaan | `docs/spec/tasks.md` |
| Status kerja, keputusan di luar spesifikasi, jebakan lingkungan | `docs/CATATAN-SESI.md` |

## Tech stack
| Layer | Pilihan |
|---|---|
| Backend/API | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 + Alembic |
| Worker | Proses Python terpisah; antrean = tabel `jobs` di SQLite (tanpa Redis/Celery) |
| Database | SQLite (WAL) di `{KLIPIN_HOME}/klipin.db` |
| Frontend | React 18 + Vite + TypeScript, Tailwind, TanStack Query, hls.js |
| Real-time UI | Server-Sent Events `GET /api/v1/events` |
| Media | yt-dlp, FFmpeg/FFprobe (libx264, libass) |
| Deteksi wajah | MediaPipe (fallback OpenCV DNN), lokal di CPU |
| Transkripsi | Adapter `Transcriber`: Deepgram (default), AssemblyAI |
| LLM | Adapter `HighlightJudge`/`Translator`/`CaptionWriter`: Anthropic Claude API |
| Rahasia | `keyring` (fallback `.env`) |
| Unggah | Paket Unggah manual (MVP); adapter `Publisher` per platform (v1.1) |
| Tes | pytest, hypothesis, respx, Playwright |

## Perintah
- Install: `uv sync` lalu `cd frontend && pnpm install`
- Jalankan lokal (API + Worker): `uv run klipin start`
- Mode dev: `uv run klipin api --reload`, `uv run klipin worker`, `cd frontend && pnpm dev`
- Cek prasyarat: `uv run klipin doctor`
- Tes backend: `KLIPIN_PROVIDERS=fake uv run pytest`
- Tes E2E: `cd frontend && pnpm exec playwright test`
- Migrasi database: `uv run alembic revision --autogenerate -m "..."` lalu `uv run alembic upgrade head`
- Build UI: `cd frontend && pnpm build` (hasil `frontend/dist` disajikan FastAPI)
- Lint: `uv run ruff check . && cd frontend && pnpm lint`

## Cara kerja
1. Baca `docs/CATATAN-SESI.md`, lalu ambil task berikutnya yang belum dicentang di `docs/spec/tasks.md`. Kerjakan **satu task per langkah**.
2. Sebelum menulis kode, baca FR yang dirujuk task itu beserta kriteria penerimaannya, BR terkait, dan TC di `09-testing.md`.
3. Setelah selesai: jalankan tes, pastikan "Selesai jika" terpenuhi, centang task, lalu ringkas apa yang berubah.
4. Jika spesifikasi kurang jelas atau saling bertentangan: **berhenti dan tanya**. Jangan menebak. Usulkan perubahan ke dokumen spesifikasi terkait (naikkan versi + baris Riwayat Perubahan).
5. Jangan menambah fitur di luar task yang sedang dikerjakan. Fitur v1.1 (unggah otomatis, analisis live bertahap) jangan dikerjakan sebelum MVP selesai.
6. Jangan menjalankan tes yang memanggil API berbayar atau memposting ke akun sungguhan. Pakai `KLIPIN_PROVIDERS=fake` dan fixture `tests/fixtures/`.
7. Keputusan yang diambil di luar spesifikasi, pekerjaan yang ditunda ke task lain, dan perubahan posisi kerja dicatat di `docs/CATATAN-SESI.md` pada commit yang sama.

## Aturan wajib
- Pakai nama entitas, status, dan enum **persis** seperti di Kamus Istilah PRD dan `05-database.md` §6 (mis. `candidate`, `approved`, `rendered`; `manual`/`auto`).
- Satu pengguna, tanpa login, tetapi **setiap** request `/api/v1/*` wajib lolos cek token sesi (`X-Klipin-Token` atau `?t=` untuk media/SSE) dan header `Host` loopback (ADR-009). Callback OAuth hanya dilindungi `state` sekali pakai. Server hanya bind ke `127.0.0.1` dan `::1`.
- Path file media selalu dibangun dari ID di database atau pengaturan, **tidak pernah** dari input path pengguna (kecuali `/fs/list` & `/streams/local`, yang hanya membaca metadata/file video).
- Transisi status hanya sesuai state machine `03-user-flow.md` §4; transisi tidak valid → `409 INVALID_STATE`.
- Aturan yang bisa dijaga database (durasi Klip 15–90 detik saat disetujui, BR-009 satu Unggahan aktif per platform, CHECK enum) dijaga dengan constraint, bukan hanya di kode.
- Posisi media disimpan sebagai integer milidetik `*_ms` relatif awal Stream Sumber; waktu kejadian disimpan UTC ISO-8601 (BR-010).
- Pekerjaan lama (unduh, transkripsi, deteksi, skor, render, unggah) **selalu** lewat Job + Worker, tidak di dalam request HTTP. Job wajib menulis progres, `checkpoint` agar bisa dilanjutkan, dan bisa dibatalkan.
- Validasi input di server (`02-requirements.md` §3), bukan hanya di form.
- Jangan pernah commit secret. API key & token OAuth hanya di keyring (atau `.env` lokal), tidak pernah di DB, log, atau respons API. Env var baru → tambahkan ke `.env.example` dan `04-arsitektur.md` §8.2.
- Perubahan skema database selalu lewat migrasi Alembic.
- Pesan error untuk pengguna dalam **Bahasa Indonesia** (pakai teks `08-ui-ux.md` §7 bila ada); detail teknis hanya masuk log.
- Panggilan ke penyedia luar selalu lewat adapter (`providers/`, `publishing/`) dengan timeout, retry sesuai `07-integrasi.md`, dan implementasi palsu untuk tes.
- Jangan menulis harga layanan atau nama model LLM secara hardcode; ambil dari `settings` (`llm_models`).

## Konvensi kode
- Backend: `backend/klipin/` sesuai `04-arsitektur.md` §6. Route FastAPI tipis (`api/routes/`) → logika di modul domain (`highlight/`, `layout/`, `subtitles/`, `media/`, `publishing/`). Handler Job di `worker/handlers/{job_type}.py`.
- Penamaan Python `snake_case`, kelas `PascalCase`; skema Pydantic di `api/schemas/` dengan nama `{Entitas}{Aksi}Request/Response`.
- Frontend: `frontend/src/pages/` per P-xx (mis. `P04ReviewKlip.tsx`), komponen bersama di `components/`, akses API hanya lewat `src/api/`. Teks UI Bahasa Indonesia.
- Tes: `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/e2e/`. Nama tes menyebut TC bila ada (mis. `test_tc025_candidates_valid`).
- Commit: `T-0xx: ringkasan singkat` (bahasa Indonesia atau Inggris, konsisten), satu task per commit bila memungkinkan.
