# Klipin: Paket Spesifikasi
> Dibuat dengan Rancang · 2026-11-20

Klipin adalah aplikasi web lokal untuk satu pengguna yang mengubah livestream YouTube dan Kick (VOD atau live) menjadi klip vertikal 9:16 siap posting. Klipin mentranskripsi audio, mendeteksi posisi cam untuk menyusun layout sesuai jenis stream, dan meranking momen highlight dari gabungan sinyal audio, chat, dan analisis AI. Klip yang disetujui diberi subtitle otomatis, dirender menjadi MP4 + .srt, lalu diunggah manual lewat Paket Unggah atau, mulai v1.1, otomatis ke YouTube, TikTok, Instagram, dan Facebook.

## Ringkasan
| Aspek | Isi |
|---|---|
| Kompleksitas | Menengah (skor 4) |
| Peran pengguna | 1 (Pengguna, tanpa login, aplikasi lokal) |
| Fitur | 17 fitur (F-01 s/d F-17); MVP mencakup 14, unggah otomatis (F-11, F-12) dan analisis live bertahap (F-07) di v1.1 |
| Kebutuhan fungsional | 27 FR, 14 BR, 12 NFR |
| Halaman | 9 (P-01 s/d P-09) |
| Kasus uji | 73 TC (TC-001–TC-066, TC-070–TC-076) |
| Task implementasi MVP | 62 (T-001 s/d T-062) |

## Tech Stack
| Layer | Pilihan |
|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind, TanStack Query, hls.js |
| Backend/API | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic |
| Worker & antrean | Proses Python terpisah + tabel `jobs` di SQLite |
| Database | SQLite (WAL), lokal |
| Auth | Tanpa login; token sesi API lokal + bind loopback; OAuth 2.0 per platform untuk unggah otomatis |
| Media | yt-dlp + FFmpeg (libx264, libass) |
| Deteksi wajah | MediaPipe / OpenCV, lokal |
| Transkripsi | Deepgram (default) / AssemblyAI, lewat adapter |
| LLM | Anthropic Claude API, lewat adapter |
| Unggah | Paket Unggah manual (MVP); YouTube Data API, TikTok Content Posting API, Instagram Graph API, Facebook Reels Publishing API (v1.1) |
| Hosting/Deploy | Berjalan di komputer Pengguna (Windows/macOS), `uv run klipin start` |

## Daftar Dokumen
| # | Dokumen | Versi | Isi |
|---|---|---|---|
| 1 | [PRD](./01-prd.md) | 1.2 | Tujuan & metrik, peran, lingkup MVP, 17 fitur, user story, Kamus Istilah, risiko |
| 2 | [Spesifikasi Kebutuhan](./02-requirements.md) | 1.2 | FR-001–FR-027 dengan kriteria Given/When/Then, aturan bisnis, validasi, NFR, matriks penelusuran |
| 3 | [User Flow & State](./03-user-flow.md) | 1.2 | UF-01–UF-08, alur error, state machine Stream Sumber, Job, Klip, Unggahan |
| 4 | [Arsitektur Sistem](./04-arsitektur.md) | 1.2 | Komponen, pipeline Job, tech stack, ADR-001–ADR-009, struktur folder, env, instalasi & runbook lokal |
| 5 | [Skema Database](./05-database.md) | 1.2 | ERD, 16 tabel, DDL SQLite tervalidasi, enum, seed, format JSON, retensi |
| 6 | [Spesifikasi API](./06-api.md) | 1.2 | Konvensi & keamanan lokal, 75 endpoint, SSE, media |
| 7 | [Integrasi Pihak Ketiga](./07-integrasi.md) | 2.0 | yt-dlp, chat, transkripsi, LLM, OAuth & unggah per platform, Paket Unggah manual, batasan audit |
| 8 | [UI/UX & Daftar Halaman](./08-ui-ux.md) | 1.1 | Prinsip, peta halaman, detail P-01–P-09, design token, pintasan keyboard, teks UI |
| 9 | [Rencana Pengujian](./09-testing.md) | 1.1 | Strategi, TC-001–TC-076, uji keamanan lokal, NFR, evaluasi kualitas & A/B transkripsi |
| 10 | [Roadmap & Milestone](./10-roadmap.md) | 1.0 | M0 → MVP-1 → MVP-2 → v1.1, ketergantungan, risiko jadwal, Definition of Done |
| — | [Tasks Implementasi](./tasks.md) | 1.0 | 62 task berurutan dengan checkpoint per fase |
| — | `CLAUDE.md` (root repo) | — | Aturan & rujukan untuk Claude Code |

## Pertanyaan Terbuka yang Belum Terjawab
**Perlu dijawab sebelum fase terkait (tidak menghalangi mulai T-001):**
- Stream mana yang dipakai sebagai Set Evaluasi untuk A/B transkripsi & evaluasi kualitas? (09-testing.md, sebelum T-061/T-062)
- Apakah opsi deteksi bahasa Deepgram untuk audio pre-recorded tersedia? Jika tidak, pakai AssemblyAI/LLM atau pilih bahasa saat impor. (07-integrasi.md, saat T-027/T-028)
- Target tanggal MVP-1, jika ada. (10-roadmap.md)

**Untuk v1.1 (unggah otomatis):**
- Mau mengajukan audit di YouTube dan/atau TikTok agar unggahan otomatis bisa publik? (07-integrasi.md)
- Urutan prioritas platform otomatis (default TikTok → Instagram → Facebook → YouTube). (01-prd.md, 10-roadmap.md)
- Izin Meta tanpa App Review untuk akun yang berperan di aplikasi sendiri; nama scope TikTok Direct Post; masa berlaku refresh token Google project Testing (dikonfirmasi saat implementasi). (07-integrasi.md)
- Apakah ada akun uji terpisah per platform? (09-testing.md)
- Ketentuan Kick untuk chat live via WebSocket publik; keandalan chat replay Kick. (01-prd.md, 07-integrasi.md)

**Preferensi produk (boleh diputuskan kapan saja):**
- Dukungan VTuber/avatar di preset Gaming. (01-prd.md)
- Kata reaksi chat per Kanal. (02-requirements.md)
- Notifikasi desktop OS saat pipeline/unggah selesai. (03-user-flow.md, 08-ui-ux.md)
- Installer satu-klik vs jalan dari repo. (04-arsitektur.md)
- Riwayat versi edit Klip (undo antar sesi). (05-database.md)
- Ekspor/impor Preset Layout & Gaya Subtitle. (06-api.md)
- Mode review cepat layar penuh. (08-ui-ux.md)

## Cara Memakai dengan Claude Code
1. Simpan folder ini sebagai `docs/spec/` di repo proyek, dan letakkan `CLAUDE.md` di root repo.
2. Pasang prasyarat: Python 3.11+, uv, Node.js 20 + pnpm, FFmpeg 6+ (dengan libx264 & libass).
3. Buka repo di Claude Code lalu ketik: "Baca CLAUDE.md dan docs/spec/tasks.md, lalu kerjakan T-001." Lanjutkan per task atau per fase, dan cek tiap Checkpoint sebelum pindah fase.
4. Untuk mode otomatis di v1.1, buat aplikasi developer sendiri di Google, TikTok, dan Meta (panduan di 04-arsitektur.md §8.3 dan 07-integrasi.md).
