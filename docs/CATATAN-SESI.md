# Catatan Sesi: status kerja & keputusan di luar spesifikasi

Dibaca agent sebelum melanjutkan task di device mana pun. Riwayat percakapan dan memori agent
tidak ikut ter-clone, jadi semua yang penting dicatat di sini. Spesifikasi di `docs/spec/`
tetap sumber kebenaran; file ini hanya mencatat hal yang belum (atau tidak) masuk ke sana.

Terakhir diperbarui: 2026-11-21, setelah T-040.

## Posisi kerja

- Fase 0 (T-001–T-007) dan Fase 1 (T-008–T-020) selesai; Checkpoint 0 & 1 lulus.
- Fase 2 dimulai atas permintaan pemilik (2026-11-21). T-021–T-040 selesai; task berikutnya: **T-041** (P-04 Review Klip, frontend).
- Satu commit per task, format `T-0xx: ringkasan`. CI GitHub Actions (ubuntu + windows) wajib hijau.
- Tes: `KLIPIN_PROVIDERS=fake uv run pytest` (413 tes setelah T-040); frontend `pnpm lint && pnpm build`.

## Keputusan di luar spesifikasi

Keputusan baru dicatat di sini dengan status **Menunggu** (jangan diubah tanpa bertanya).
Setelah pemilik menyetujui, isinya dipindah ke dokumen spesifikasi terkait (bagian
"Keputusan implementasi", versi naik + baris Riwayat Perubahan) dan baris di sini tinggal
indeks. Per 2026-11-21 semua keputusan #1–#35 sudah disetujui; nomor berikutnya: #36.

| # | Ringkas | Status |
|---|---|---|
| 1 | Palet & font 08-ui-ux | Disetujui pemilik |
| 2 | Membatalkan Job pipeline (download/transcribe/detect_layout/score_highlights seluruh strea | Disetujui 2026-11-21, isi lengkap di `03-user-flow.md v1.3` § Keputusan implementasi |
| 3 | Koneksi SSE ke-6 ditolak 429 dengan kode baru TOO_MANY_CONNECTIONS (belum ada di tabel err | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 4 | Pengaturan max_heavy_jobs menang atas env (dibalik dari keputusan awal) | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 5 | Pengaturan transcriber_provider/llm_provider menang atas env KLIPIN_TRANSCRIBER/KLIPIN_LLM | Disetujui pemilik (2026-11-21) |
| 6 | Respons Job memuat stream_title (untuk kolom "Objek" P-06); event SSE job | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 7 | GET /system/health = cek klipin doctor tanpa cek port (port dipakai server itu sendiri); r | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 8 | update-ytdlp = uv lock --upgrade-package yt-dlp lalu uv sync --no-install-project --inexac | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 9 | Validasi PATCH /settings untuk kunci yang tidak punya aturan di 02-requirements | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 10 | Fixture audio "tenang" = hening digital (nada pelan membuat FLAC > 6 MB); fixture wajah da | Disetujui (sumber CC0/PD dipilih pemilik) |
| 11 | media/ytdlp | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 12 | estimated_size_bytes = jumlah filesize/filesize_approx format terpilih (fallback tbr × dur | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 13 | Bentuk respons GET /streams (tidak dirinci di 06-api | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 14 | Nilai fields error dikirim sebagai string (required_bytes, free_bytes, existing_stream_id) | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 15 | Kata reaksi (FR-010) | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 16 | Jenis Pesan Chat | Disetujui 2026-11-21, isi lengkap di `05-database.md v1.4` § Keputusan implementasi |
| 17 | Job download | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 18 | Mode fake memakai media fixture (media/fake | Disetujui pemilik (2026-11-21), dipindah ke 04-arsitektur.md v1.3 §8.2 |
| 19 | P-01 | Disetujui 2026-11-21, isi lengkap di `08-ui-ux.md v1.2` § Keputusan implementasi |
| 20 | P-02 | Disetujui 2026-11-21, isi lengkap di `08-ui-ux.md v1.2` § Keputusan implementasi |
| 21 | Transcriber | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 22 | Job transcribe | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 23 | Adapter Deepgram | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 24 | Transcriber | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 25 | FR-022 | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 26 | detect_layout | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 27 | Filtergraph preset statis (media/ffmpeg | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 28 | Jalur crop dinamis (layout/crop_path | Disetujui 2026-11-21, isi lengkap di `04-arsitektur.md v1.4` § Keputusan implementasi |
| 29 | Bentuk respons yang tidak dirinci di 06-api | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |
| 30 | Sinyal Audio | Disetujui 2026-11-21, isi lengkap di `02-requirements.md v1.3` § Keputusan implementasi |
| 31 | Sinyal Chat | Disetujui 2026-11-21, isi lengkap di `02-requirements.md v1.3` § Keputusan implementasi |
| 32 | Pra-seleksi BR-003 (highlight/preselect | Disetujui 2026-11-21, isi lengkap di `02-requirements.md v1.3` § Keputusan implementasi |
| 33 | HighlightJudge (providers/llm/) | Disetujui 2026-11-21, isi lengkap di `07-integrasi.md v2.4` § Keputusan implementasi |
| 34 | score_highlights | Disetujui 2026-11-21, isi lengkap di `02-requirements.md v1.3` § Keputusan implementasi |
| 35 | Endpoint Klip (clips | Disetujui 2026-11-21, isi lengkap di `06-api.md v1.3` § Keputusan implementasi |

## Sengaja ditunda ke task tertentu

| Hal | Ke task |
|---|---|
| `providers/*.json` (respons rekaman per penyedia) dibuat dari dokumentasi resmi bersama adapternya (Deepgram T-028, AssemblyAI T-029, Anthropic judge T-038 sudah) | T-044, T-056 |
| Status Klip saat Job `render` sukses/gagal (pipeline baru menangani stream) | T-046 |
| `cancel` pada `record_live` = `stop` (gabung segmen) ; event `live.position` | T-051 |
| Tab P-07 Akun Unggah, Caption, Gaya Subtitle (sengaja belum ditampilkan) | v1.1, T-050, T-045 |
| Analisis live per blok (scope transcribe/score) | v1.1 (FR-013) |
| `POST /streams` mode `live` sementara ditolak 400 "Rekam live belum tersedia di versi ini."; tombol Rekam Live & checkbox "Analisis selama live" di P-01 | T-051, T-053 |
| Transkripsi rentang (Penanda Live) belum mencegah kata ganda dengan transkripsi seluruh stream sesudahnya ("hanya rentang yang belum ditranskripsi") | T-051, T-052 |
| Tombol "Pilih file dari komputer" di P-01 | T-054 |
| Aksi "Hapus video sumber" / "Hapus stream" di P-02 | T-055 |
| Badge "Kanal dikenal: preset X tersimpan" | T-034 |

## Cara kerja yang sudah berjalan

- **Job dummy**: dengan `KLIPIN_PROVIDERS=fake`, Jenis Job tanpa handler asli memakai handler palsu
  (`worker/handlers/fake.py`, 20 langkah × 0,5 dtk, lanjut dari checkpoint). Pipeline palsu berjalan
  penuh `download → detect_layout + transcribe → score_highlights → ready`. Handler asli
  didaftarkan dengan `@register("jenis")` dan otomatis menggantikan yang palsu. Modul handler
  baru wajib diimpor di bagian bawah `worker/handlers/__init__.py` agar `@register` berjalan.
- **DB uji**: buat Job dummy dengan `INSERT` ke `source_streams` + `jobs` di `KLIPIN_HOME` sementara.
- **Keyring**: tes memakai keyring di memori (`tests/conftest.py`). Uji UI dengan server sungguhan
  menulis ke keyring OS asli; hapus lagi entri `klipin/*` setelahnya.
- **Migrasi**: DDL & seed disalin apa adanya dari 05-database.md ke `db/migrations/versions/*.sql`.
  Model dijaga sama lewat tes `test_models_match_migrations`; FK dan index DESC dikecualikan dari
  autogenerate karena reflection SQLite tidak membaca `ON DELETE`/`DESC`.

## Jebakan lingkungan (Windows)

- Jangan mengedit file lewat PowerShell 5.1 `Get-Content`/`Set-Content`: UTF-8 tanpa BOM dibaca
  sebagai ANSI dan ditulis ulang rusak (`§` → `Â§`, emoji → `ðŸ˜‚`). Pakai tool Write/Edit atau
  Python dengan `encoding="utf-8"`.
- Heredoc panjang di tool Bash sering gagal di-parse; pakai tool Write.
- Python yang mencetak emoji ke pipe kena `UnicodeEncodeError` cp1252; cetak dengan `ascii(...)`.
- TypeScript dipin `~6.0` karena typescript-eslint belum mendukung TypeScript 7.
- `astral-sh/setup-uv` tidak menerbitkan tag mayor; pin versi lengkap (`v10.3.3`).
- Ruff di proyek ini mengaktifkan aturan tambahan (FURB, BLE, SIM, ISC); Python minimal 3.11
  (jangan pakai sintaks generik 3.12).
- Di perangkat dengan repo di `D:\Projects\klipin`, awalnya tidak ada `uv`/`pnpm` di PATH: `uv` dipasang lewat
  `python -m pip install --user uv` (biner di `%APPDATA%\Python\Python312\Scripts`). FFmpeg ada di
  `D:\App klip\ffmpeg-8.1.1-essentials_build\bin`.
- Mode `fake` (dev/E2E) kini menjalankan `transcribe` asli: butuh FFmpeg di PATH dan API key
  transkripsi terisi (nilai sembarang) di Pengaturan; tanpa key Job gagal sesuai TC-014.
- Di tes, jangan `del HANDLERS[...]` untuk mengembalikan handler: itu ikut menghapus handler
  asli untuk tes berikutnya. Pakai `monkeypatch.setitem/delitem(HANDLERS, ...)`.
- CI memasang FFmpeg (apt / choco) karena tes handler memakai FFmpeg asli.
- `pnpm` tidak ada di PATH: jalankan lewat `corepack pnpm …` (versi dipin `packageManager`).
  Uji UI manual: `.claude/launch.json` (tidak di-commit) menjalankan `uv run klipin start` dengan
  `KLIPIN_PROVIDERS=fake` dan `KLIPIN_HOME` di folder sementara.
- `netstat` tidak menampilkan socket proses dari sandbox agent; verifikasi bind lewat akses IP LAN.

## Pertanyaan terbuka untuk pemilik proyek

- Uji API berbayar sungguhan (Deepgram FLAC, `max_tokens` 300 LLM, label pembicara AssemblyAI
  untuk `id`) **ditunda ke T-061** (keputusan pemilik 2026-11-21).
- Nama model `llm_models` diisi pemilik sendiri lewat P-07; sampai diisi, mode real memakai skor
  parsial (Audio + Chat).
- Folder kerja: `.env` lokal di perangkat ini berisi `KLIPIN_HOME=D:\Klipin` (tidak di-commit).
- Pertanyaan terbuka bawaan spesifikasi tetap berlaku (lihat `docs/spec/00-README.md` dan bagian
  "Asumsi & Pertanyaan Terbuka" tiap dokumen).
