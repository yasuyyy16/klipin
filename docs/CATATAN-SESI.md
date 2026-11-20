# Catatan Sesi: status kerja & keputusan di luar spesifikasi

Dibaca agent sebelum melanjutkan task di device mana pun. Riwayat percakapan dan memori agent
tidak ikut ter-clone, jadi semua yang penting dicatat di sini. Spesifikasi di `docs/spec/`
tetap sumber kebenaran; file ini hanya mencatat hal yang belum (atau tidak) masuk ke sana.

Terakhir diperbarui: 2026-11-20, setelah Checkpoint 1.

## Posisi kerja

- Fase 0 (T-001–T-007) dan Fase 1 (T-008–T-020) selesai; Checkpoint 0 & 1 lulus.
- Task berikutnya: **T-021** (Fase 2). Mulai Fase 2 hanya setelah pemilik proyek konfirmasi.
- Satu commit per task, format `T-0xx: ringkasan`. CI GitHub Actions (ubuntu + windows) wajib hijau.
- Tes: `KLIPIN_PROVIDERS=fake uv run pytest` (170 tes per Checkpoint 1); frontend `pnpm lint && pnpm build`.

## Keputusan di luar spesifikasi

Status **menunggu**: belum disetujui pemilik; jangan diubah tanpa bertanya, dan setelah
disetujui pindahkan ke dokumen spesifikasi terkait (naikkan versi + baris Riwayat Perubahan).

| # | Keputusan | Di mana | Status |
|---|---|---|---|
| 1 | Palet & font 08-ui-ux.md §5 (ungu `#7C5CFF`, latar `#0F1115`, Inter) **dipertahankan** walau antislop menandainya | `frontend/src/styles/index.css` | Disetujui pemilik |
| 2 | Membatalkan Job pipeline (download/transcribe/detect_layout/score_highlights seluruh stream) membuat Stream Sumber `failed` dengan pesan "Job dibatalkan." State machine §4.1 tidak mengatur ini; tanpanya stream tertahan di `downloading`/`processing` | `backend/klipin/jobs.py` (`cancel_job`) | Menunggu |
| 3 | Koneksi SSE ke-6 ditolak `429` dengan kode baru `TOO_MANY_CONNECTIONS` (belum ada di tabel error 06-api.md §1) | `api/routes/events.py` | Menunggu, usul tambah ke 06-api.md |
| 4 | Env yang diisi eksplisit menang atas Pengaturan: `KLIPIN_MAX_HEAVY_JOBS` vs `settings.max_heavy_jobs` | `worker/loop.py` (`max_heavy_jobs`) | Menunggu |
| 5 | Pertanyaan yang sama untuk `KLIPIN_TRANSCRIBER`/`KLIPIN_LLM_PROVIDER` vs `transcriber_provider`/`llm_provider`; belum dipakai di kode | Putuskan sebelum T-026/T-028 | Belum diputuskan |
| 6 | Respons Job memuat `stream_title` (untuk kolom "Objek" P-06); event SSE `job.updated` memuat `started_at`/`finished_at` | `api/routes/jobs.py`, `api/routes/events.py` | Menunggu, usul tambah ke 06-api.md |
| 7 | `GET /system/health` = cek `klipin doctor` tanpa cek port (port dipakai server itu sendiri); respons `{ok, checks[], home, backup_dir}` | `api/routes/system.py` | Menunggu (skema tidak dirinci di spesifikasi) |
| 8 | `update-ytdlp` = `uv lock --upgrade-package yt-dlp` lalu `uv sync --no-install-project --inexact`; mengubah `uv.lock`. Di mode `fake` hanya simulasi | `backend/klipin/system.py` | Menunggu |
| 9 | Validasi PATCH /settings untuk kunci yang tidak punya aturan di 02-requirements.md §3: `score_min_threshold` 0–100, `live_last_n_default_s` 15–90, enum penyedia, `default_subtitle_style` harus ada di DB, kunci asing ditolak | `api/schemas/settings.py` | Menunggu |
| 10 | Fixture audio "tenang" = hening digital (nada pelan membuat FLAC > 6 MB); fixture wajah dari 2 video domain publik Wikimedia Commons | `tests/fixtures/README.md` | Disetujui (sumber CC0/PD dipilih pemilik) |

## Sengaja ditunda ke task tertentu

| Hal | Ke task |
|---|---|
| `POST /jobs/{id}/confirm` dengan `range`, `usage_estimate`, `pricing_links`; konfirmasi otomatis di pipeline (`awaiting_confirmation`). URL halaman harga penyedia **tidak ada** di spesifikasi, jangan ditebak | T-030 |
| `providers/*.json` (respons rekaman per penyedia) dibuat dari dokumentasi resmi bersama adapternya | T-028, T-029, T-038 |
| Model MediaPipe: versi 1.2.3 tidak menyertakan `solutions` maupun model wajah; perlu unduh `.tflite` (minta izin). Uji deteksi fixture wajah + IoU TC-015 terjadi di sini | T-031 |
| Status Klip saat Job `render` sukses/gagal (pipeline baru menangani stream) | T-046 |
| `cancel` pada `record_live` = `stop` (gabung segmen) ; event `live.position` | T-051 |
| Tab P-07 Akun Unggah, Caption, Gaya Subtitle (sengaja belum ditampilkan) | v1.1, T-050, T-045 |
| Analisis live per blok (scope transcribe/score) | v1.1 (FR-013) |

## Cara kerja yang sudah berjalan

- **Job dummy**: dengan `KLIPIN_PROVIDERS=fake`, Jenis Job tanpa handler asli memakai handler palsu
  (`worker/handlers/fake.py`, 20 langkah × 0,5 dtk, lanjut dari checkpoint). Pipeline palsu berjalan
  penuh `download → detect_layout + transcribe → score_highlights → ready`. Handler asli
  didaftarkan dengan `@register("jenis")` dan otomatis menggantikan yang palsu.
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
- `netstat` tidak menampilkan socket proses dari sandbox agent; verifikasi bind lewat akses IP LAN.

## Pertanyaan terbuka untuk pemilik proyek

- Keputusan #2–#9 di atas: setujui atau ubah.
- Ruang disk C: sekitar 33 GB (disarankan ≥ 50 GB); kosongkan atau arahkan `KLIPIN_HOME` ke drive
  lain sebelum mengunduh VOD sungguhan di Fase 2.
- Pertanyaan terbuka bawaan spesifikasi tetap berlaku (lihat `docs/spec/00-README.md`).
