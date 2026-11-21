# Spesifikasi API: Klipin
> Versi 1.3 · 2026-11-21 · Status: Draf · Dokumen terkait: 02-requirements.md, 03-user-flow.md, 04-arsitektur.md, 05-database.md, 07-integrasi.md

API ini hanya dipakai oleh Web UI Klipin sendiri (React SPA) di komputer yang sama. API tidak dirancang untuk publik.

## 1. Konvensi
- **Base URL:** `http://127.0.0.1:8765/api/v1` atau `http://localhost:8765/api/v1` (port dari `KLIPIN_PORT`). Server hanya bind ke alamat loopback `127.0.0.1` dan `::1` (BR-012).
- **Format:** JSON UTF-8, `snake_case`. Waktu kejadian ISO-8601 UTC (`2026-11-20T04:33:00Z`). Posisi media integer milidetik `*_ms` (BR-010).
- **Autentikasi:** tidak ada login (satu Pengguna). Untuk mencegah situs lain di browser memanggil API lokal (CSRF/DNS rebinding):
  - Saat start, server membuat **token sesi acak** (32 byte) dan menyisipkannya ke `index.html` (`<meta name="klipin-token">`).
  - Semua request `/api/v1/*` (callback OAuth `GET /oauth/callback/{platform}` berada di luar `/api/v1` dan dilindungi `state`) **wajib** mengirim header `X-Klipin-Token: {token}`; tanpa/salah → `403 FORBIDDEN_ORIGIN`.
  - Header `Host` wajib `127.0.0.1:{port}` atau `localhost:{port}`; lainnya → `403`.
  - Tidak ada header CORS (`Access-Control-Allow-Origin` tidak dikirim).
  - SSE dan URL media (dipakai di `<video src>`, yang tidak bisa memasang header) memakai query `?t={token}`.
- **Format error standar:**
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Durasi klip harus 15–90 detik.", "fields": { "end_ms": "Durasi klip harus 15–90 detik." } } }
```
| Kode | HTTP | Kapan |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Input tidak lolos validasi (02-requirements.md bagian 3) |
| `URL_NOT_SUPPORTED` | 400 | URL bukan YouTube/Kick atau tidak bisa di-resolve |
| `FORBIDDEN_ORIGIN` | 403 | Token/Host salah |
| `NOT_FOUND` | 404 | Resource tidak ada |
| `INVALID_STATE` | 409 | Transisi status tidak diizinkan (03-user-flow.md bagian 4) |
| `DUPLICATE_UPLOAD` | 409 | BR-009 (sudah ada Unggahan aktif/berhasil untuk platform itu) |
| `AUTO_NOT_AVAILABLE` | 409 | Mode `auto` diminta padahal BR-013 tidak terpenuhi |
| `PLATFORM_NOT_CONFIGURED` | 409 | Kredensial aplikasi developer platform belum diisi |
| `INSUFFICIENT_DISK` | 409 | Ruang disk kurang |
| `SOURCE_DELETED` | 409 | Video sumber sudah dihapus (FR-024) |
| `SECRET_MISSING` | 409 | API key/akun belum dikonfigurasi |
| `UPSTREAM_ERROR` | 502 | yt-dlp/penyedia API mengembalikan error saat request sinkron |
| `INTERNAL_ERROR` | 500 | Error tak terduga (detail hanya di log) |
- **Pagination:** offset sederhana `?limit=50&offset=0` (maks. `limit` 200), respons `{ "items": [...], "total": 123 }`. Data per Stream Sumber jarang > 200 Klip, jadi cursor tidak diperlukan.
- **Operasi lama** (unduh, transkripsi, render, unggah) tidak pernah dikerjakan di dalam request: endpoint membuat Job dan mengembalikan `202` + objek Job. Progres dikirim lewat SSE (`GET /events`).
- **Idempotensi:** aksi status (`approve`, `render`, `uploads`) memeriksa status saat ini di dalam transaksi; panggilan ganda menghasilkan `409 INVALID_STATE`/`DUPLICATE_UPLOAD`, bukan Job ganda.

## 2. Daftar Endpoint
Semua dipakai peran **Pengguna**.

| Method | Path | Deskripsi | FR |
|---|---|---|---|
| POST | `/streams/inspect` | Cek URL & ambil metadata tanpa membuat data | FR-001, FR-003 |
| POST | `/streams` | Buat Stream Sumber dari URL VOD/live (+ Job `download`/`record_live`) | FR-001, FR-003 |
| POST | `/streams/local` | Buat Stream Sumber dari path file lokal | FR-002 |
| GET | `/fs/list` | Jelajah folder lokal untuk memilih file | FR-002 |
| GET | `/streams` | Daftar Stream Sumber (filter status, ukuran file) | FR-024 |
| GET | `/streams/{id}` | Detail Stream Sumber + ringkasan Job & Klip | FR-001 |
| POST | `/streams/{id}/stop` | Berhenti rekam live | FR-003 |
| POST | `/streams/{id}/rescore` | Hitung ulang Skor Highlight dengan bobot terbaru | FR-012 |
| DELETE | `/streams/{id}/source-video` | Hapus video sumber saja | FR-024 |
| DELETE | `/streams/{id}` | Hapus Stream Sumber beserta data turunannya | FR-024 |
| GET | `/streams/{id}/transcript` | Segmen & kata dalam rentang waktu | FR-014, FR-015 |
| GET | `/streams/{id}/timeline` | Data heatmap timeline (Sinyal per jendela) | FR-014 |
| GET | `/streams/{id}/waveform` | Puncak amplitudo audio untuk trimmer | FR-015 |
| GET | `/streams/{id}/regions` | Region Cam hasil deteksi + preset tersaran | FR-006 |
| POST | `/streams/{id}/markers` | Buat Penanda Live | FR-004 |
| PATCH | `/markers/{id}` | Akhiri penanda "Tandai Mulai" | FR-004 |
| GET | `/streams/{id}/markers` | Daftar Penanda Live | FR-004 |
| GET | `/streams/{id}/clips` | Daftar Klip | FR-014 |
| POST | `/streams/{id}/clips` | Buat Klip manual dari rentang | FR-014 |
| POST | `/streams/{id}/clips/render-approved` | Render semua Klip `approved` | FR-018 |
| GET | `/clips/{id}` | Detail Klip (layout, region efektif, subtitle) | FR-014, FR-015 |
| PATCH | `/clips/{id}` | Edit rentang, preset, gaya, bahasa, judul, override subtitle | FR-015, FR-016, FR-017 |
| POST | `/clips/{id}/approve` | Setujui | FR-014 |
| POST | `/clips/{id}/reject` | Tolak | FR-014 |
| POST | `/clips/{id}/restore` | Pulihkan dari `rejected` | FR-014 |
| POST | `/clips/{id}/unapprove` | Batalkan persetujuan | FR-014 |
| POST | `/clips/{id}/snap` | Hitung titik jepret ke batas kalimat | FR-015 |
| PUT | `/clips/{id}/regions` | Set Region Cam override Klip (+ opsi simpan default Kanal) | FR-008, FR-015 |
| GET | `/clips/{id}/subtitles` | Baris subtitle efektif (setelah override/terjemahan) | FR-016 |
| POST | `/clips/{id}/translate` | Terjemahkan subtitle ke Indonesia | FR-016 |
| POST | `/clips/{id}/preview-render` | Render pratinjau 5 detik | FR-017 (ADR-005) |
| POST | `/clips/{id}/render` | Render Klip | FR-018 |
| GET | `/channels` | Daftar Kanal | FR-008 |
| POST | `/channels` | Buat Kanal manual (untuk file lokal) | FR-008 |
| PATCH | `/streams/{id}/channel` | Kaitkan Stream Sumber ke Kanal | FR-008 |
| GET | `/layout-presets` | Daftar Preset Layout | FR-007 |
| GET | `/subtitle-styles` | Daftar Gaya Subtitle | FR-017 |
| POST | `/subtitle-styles` | Buat/gandakan Gaya Subtitle | FR-017 |
| PATCH | `/subtitle-styles/{id}` | Ubah Gaya Subtitle (non-bawaan) | FR-017 |
| DELETE | `/subtitle-styles/{id}` | Hapus Gaya Subtitle (non-bawaan, tidak dipakai) | FR-017 |
| GET | `/jobs` | Daftar Job (aktif & riwayat) | FR-023 |
| GET | `/jobs/{id}` | Detail Job + log | FR-023 |
| POST | `/jobs/{id}/cancel` | Batalkan Job | FR-023 |
| POST | `/jobs/{id}/retry` | Coba ulang Job `failed` | FR-023 |
| POST | `/jobs/{id}/confirm` | Konfirmasi perkiraan pemakaian | FR-022 |
| GET | `/settings` | Baca Pengaturan (tanpa rahasia) | FR-021 |
| PATCH | `/settings` | Ubah Pengaturan | FR-021 |
| PUT | `/secrets/{name}` | Simpan API key ke keyring | FR-021 |
| DELETE | `/secrets/{name}` | Hapus API key | FR-021 |
| POST | `/secrets/{name}/test` | Tes koneksi penyedia | FR-021 |
| GET | `/system/health` | Hasil pemeriksaan prasyarat (setara `klipin doctor`) | FR-021 |
| POST | `/system/open-folder` | Buka folder output / folder Klip di file explorer OS | FR-018, FR-025 |
| POST | `/system/update-ytdlp` | Perbarui yt-dlp | FR-021 |
| GET | `/upload-accounts` | Status & batas keempat Platform Tujuan | FR-019 |
| GET | `/oauth/{platform}/start` | Mulai OAuth platform (redirect) | FR-019 |
| GET | `/oauth/callback/{platform}` (root, di luar `/api/v1`) | Callback OAuth platform | FR-019 |
| GET/POST | `/oauth/{platform}/targets` | Pilih Halaman Facebook / akun Instagram Professional | FR-019 |
| DELETE | `/upload-accounts/{id}` | Putuskan Akun Unggah | FR-019 |
| GET | `/clips/{id}/upload-dialog` | Data dialog unggah (kesiapan per platform + draf caption) | FR-020, FR-025, FR-027 |
| POST | `/clips/{id}/captions` | Buat/ulang draf caption per platform | FR-027 |
| PATCH | `/clips/{id}/captions` | Simpan edit draf caption | FR-027 |
| POST | `/clips/{id}/uploads` | Buat Unggahan manual/otomatis untuk beberapa platform | FR-020, FR-025 |
| GET | `/clips/{id}/uploads` | Riwayat Unggahan Klip | FR-020, FR-025 |
| POST | `/uploads/{id}/mark-posted` | Tandai Unggahan manual sudah diposting | FR-026 |
| DELETE | `/uploads/{id}` | Batalkan manual `pending` / hapus dari riwayat | FR-026 |
| POST | `/uploads/{id}/retry` | Coba ulang Unggahan otomatis yang gagal | FR-020 |
| POST | `/uploads/{id}/switch-manual` | Alihkan Unggahan gagal ke manual | FR-020, FR-025 |
| GET | `/events` | Server-Sent Events progres & perubahan status | FR-023 |
| GET | `/media/streams/{id}/source` | Video sumber (HTTP Range) | FR-014 |
| GET | `/media/streams/{id}/live.m3u8` | Playlist HLS segmen live lokal | FR-003 |
| GET | `/media/streams/{id}/segments/{name}` | Satu segmen live | FR-003 |
| GET | `/media/streams/{id}/frame` | Satu frame JPEG pada `t_ms` | FR-006, FR-007 |
| GET | `/media/clips/{id}/video` | MP4 hasil render (Range, `?download=1`) | FR-018 |
| GET | `/media/clips/{id}/srt` | File .srt | FR-018 |
| GET | `/media/clips/{id}/preview` | MP4 pratinjau 5 detik | FR-017 |

Callback OAuth berada di root (`http://localhost:8765/oauth/callback/{platform}`), bukan di `/api/v1`, agar sama persis dengan redirect URI yang didaftarkan di konsol developer tiap platform.

## 3. Detail Endpoint

### `POST /api/v1/streams/inspect`: cek URL
- **FR:** FR-001, FR-003 · **Peran:** Pengguna · **Idempoten:** ya (tanpa efek samping)
- **Request:**
```json
{ "url": "https://www.youtube.com/watch?v=abc123XYZ" }
```
- **Response 200:**
```json
{
  "platform": "youtube",
  "external_video_id": "abc123XYZ",
  "title": "Main horor sampai pagi",
  "channel": { "external_id": "UCxxxx", "name": "NamaStreamer", "known_channel_id": 4 },
  "duration_ms": 10845000,
  "is_live": false,
  "has_chat_replay": true,
  "estimated_size_bytes": 6442450944,
  "disk_free_bytes": 120259084288
}
```
- **Error:** 400 `URL_NOT_SUPPORTED`; 502 `UPSTREAM_ERROR` (yt-dlp gagal, pesan diringkas). Timeout 10 detik.

### `POST /api/v1/streams`: buat Stream Sumber dari URL
- **FR:** FR-001, FR-003 · **Peran:** Pengguna · **Idempoten:** tidak. UI menonaktifkan tombol setelah klik; jika ada Stream Sumber dengan `external_video_id` sama yang belum `failed`, respons `409 INVALID_STATE` dengan `fields.existing_stream_id`.
- **Request:**
```json
{ "url": "https://kick.com/namastreamer", "mode": "live", "live_analysis_enabled": true }
```
`mode`: `vod` atau `live`. Jika `mode = vod` tetapi URL sedang live → `409 INVALID_STATE` dengan pesan "Stream ini masih live. Gunakan Rekam Live?".
- **Response 201:**
```json
{
  "stream": { "id": 17, "source_type": "live_url", "platform": "kick", "status": "recording", "title": "…", "channel_id": 9 },
  "job": { "id": 230, "job_type": "record_live", "status": "queued" }
}
```
- **Error:** 400 `URL_NOT_SUPPORTED`/`VALIDATION_ERROR`; 409 `INSUFFICIENT_DISK` (VOD; `fields.required_bytes`, `fields.free_bytes`), `INVALID_STATE`; 502 `UPSTREAM_ERROR`.

### `POST /api/v1/streams/local`: impor file lokal
- **FR:** FR-002 · **Idempoten:** tidak
- **Request:**
```json
{ "path": "D:\\Rekaman\\stream-2026-11-18.mp4", "channel_id": null, "copy_to_workdir": false }
```
- **Response 201:** sama dengan `POST /streams`; `job` berisi Job `detect_layout`, dan `jobs` berisi kedua Job (`detect_layout`, `transcribe`).
- **Error:** 400 `VALIDATION_ERROR` (path tidak ada, ekstensi tidak didukung, tanpa audio, > 20 GB).

### `GET /api/v1/fs/list?path=D:\Rekaman`
- **FR:** FR-002 · Mengembalikan folder & file video (mp4/mkv/mov/webm) di path; tanpa `path` → daftar drive/home. Hanya membaca nama, ukuran, dan waktu ubah. Symlink tidak diikuti.
- **Response 200:** `{ "path": "D:\\Rekaman", "parent": "D:\\", "entries": [{ "name": "stream.mp4", "type": "file", "size": 5368709120, "modified_at": "…" }] }`

### `GET /api/v1/streams/{id}`
- **Response 200:**
```json
{
  "id": 12, "title": "…", "platform": "youtube", "source_type": "vod_url", "status": "ready",
  "duration_ms": 10845000, "detected_language": "en", "has_chat": true,
  "channel": { "id": 4, "name": "NamaStreamer" },
  "suggested_layout_preset": { "id": 1, "code": "gaming" },
  "storage": { "source_bytes": 6442450944, "rendered_bytes": 183500800, "source_deleted": false },
  "clip_counts": { "candidate": 11, "approved": 2, "rejected": 3, "rendered": 1 },
  "active_jobs": [{ "id": 101, "job_type": "render", "status": "running", "progress_pct": 40 }]
}
```

### `POST /api/v1/streams/{id}/stop`
- **FR:** FR-003 · **Idempoten:** ya (stream yang sudah tidak `recording` → 200 tanpa aksi)
- **Response 202:** `{ "stream": { "id": 17, "status": "recording" }, "message": "Rekaman dihentikan, segmen sedang digabung." }`. Status berubah ke `processing` via SSE.

### `POST /api/v1/streams/{id}/rescore`
- **FR:** FR-012 · Hanya jika status `ready`. Membuat Job `score_highlights` yang memakai cache `highlight_windows` (tanpa panggilan LLM baru kecuali jendela baru lolos pra-seleksi).
- **Response 202:** `{ "job": { "id": 140, "job_type": "score_highlights", "status": "queued" } }`
- **Error:** 409 `INVALID_STATE` (status bukan `ready`).

### `DELETE /api/v1/streams/{id}/source-video`
- **FR:** FR-024 · `?confirm=true` wajib. Tanpa `confirm`, respons `200` berisi pratinjau dampak: `{ "unrendered_approved_clips": 3, "bytes_to_free": 6442450944 }`.
- **Response 200 (dengan confirm):** `{ "bytes_freed": 6442450944 }`
- **Error:** 409 `INVALID_STATE` jika ada Job `running` pada stream ini.

### `DELETE /api/v1/streams/{id}`
- **FR:** FR-024 · `?confirm=true` wajib. Menghapus baris DB (CASCADE) dan folder `streams/{id}/`; file di folder output tidak dihapus.
- **Response 200:** `{ "bytes_freed": 7012345678 }` · **Error:** 409 jika ada Job `running`/`record_live` aktif.

### `GET /api/v1/streams/{id}/transcript?from_ms=3600000&to_ms=3690000`
- Rentang maks. 30 menit per request.
- **Response 200:**
```json
{ "segments": [{ "id": 881, "start_ms": 3601200, "end_ms": 3603900, "speaker": "S1", "text": "Dude he actually jumped!",
                 "words": [{ "id": 128830, "start_ms": 3601200, "end_ms": 3601450, "word": "Dude" }] }] }
```

### `GET /api/v1/streams/{id}/waveform?from_ms=3570000&to_ms=3690000&points=1200`
- **FR:** FR-015 · Rentang ≤ 10 menit, `points` ≤ 4.000. Dihitung FFmpeg dari video sumber (cache per rentang) · **Response 200:** `{ "from_ms": 3570000, "to_ms": 3690000, "peaks": [0.02, 0.15, 0.91, …] }` (nilai 0–1) · **Error:** 409 `SOURCE_DELETED`.

### `GET /api/v1/streams/{id}/timeline?bucket_ms=30000`
- **Response 200:** `{ "buckets": [{ "start_ms": 0, "audio": 0.12, "chat": 0.05, "llm": null }], "clips": [{ "id": 55, "start_ms": 3601000, "end_ms": 3655000, "status": "candidate" }] }`

### `POST /api/v1/streams/{id}/markers`: Penanda Live
- **FR:** FR-004 · **Idempoten:** tidak (setiap klik = satu penanda) · Hanya untuk Stream Sumber `recording`.
- **Request:** `{ "kind": "last_n_seconds", "seconds": 60 }` atau `{ "kind": "start_end" }` (membuka penanda; `end_ms` diisi lewat PATCH).
- **Response 201:**
```json
{ "marker": { "id": 31, "kind": "last_n_seconds", "start_ms": 1140000, "end_ms": 1200000 },
  "clip": { "id": 77, "status": "candidate", "origin": "live_marker" },
  "job": { "id": 233, "job_type": "transcribe", "is_heavy": false, "status": "queued" },
  "info": null }
```
`info` berisi "Rekaman baru 20 detik" jika rentang dipotong (FR-004).
- **Error:** 400 `VALIDATION_ERROR` (`seconds` di luar 15–90); 409 `INVALID_STATE` (stream tidak `recording`, atau masih ada penanda `start_end` terbuka).

### `PATCH /api/v1/markers/{id}`
- **Request:** `{ "end": true }` → `end_ms` = posisi rekaman sekarang. Membuat Klip + Job `transcribe` rentang.
- **Response 200:** seperti `POST /markers`, ditambah `"warning": "Durasi melebihi 90 detik"` bila berlaku.

### `GET /api/v1/streams/{id}/clips?status=candidate,approved&sort=score&limit=50&offset=0`
- `sort`: `score` (default, DESC) atau `start` (ASC). Default tanpa `status` = semua kecuali `rejected`.
- **Response 200:**
```json
{ "items": [{ "id": 55, "origin": "auto", "status": "candidate", "start_ms": 3601000, "end_ms": 3655000,
              "score": 87, "score_partial": false, "category": "hype", "reason": "Reaksi kaget besar saat jumpscare, chat meledak",
              "title": "Jumpscare paling brutal", "layout_preset_id": 1,
              "uploads": [{ "platform": "tiktok", "mode": "manual", "status": "pending" }] }],
  "total": 14 }
```

### `POST /api/v1/streams/{id}/clips`: Klip manual
- **FR:** FR-014 · **Request:** `{ "start_ms": 5000000, "end_ms": 5040000 }`
- **Response 201:** objek Klip lengkap (`origin = manual`, `status = candidate`, preset = default Kanal → preset tersaran → `center_crop`).
- **Error:** 400 (rentang di luar durasi, `start_ms ≥ end_ms`); 409 `SOURCE_DELETED`.

### `GET /api/v1/clips/{id}`
- **Response 200:**
```json
{
  "id": 55, "source_stream_id": 12, "origin": "auto", "status": "approved",
  "start_ms": 3601000, "end_ms": 3655000, "duration_ms": 54000,
  "score": 87, "score_breakdown": { "audio": 0.91, "chat": 0.84, "llm": 82, "partial": false },
  "category": "hype", "reason": "…", "title": "Jumpscare paling brutal",
  "layout_preset": { "id": 1, "code": "gaming", "params": { "cam_height_pct": 35 } },
  "regions": { "source": "channel", "items": [
      { "role": "cam", "x": 0.74, "y": 0.70, "w": 0.24, "h": 0.27 },
      { "role": "content", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0 } ] },
  "subtitle_style_id": 2, "subtitle_language": "source", "available_languages": ["source", "id"],
  "detected_language": "en",
  "needs_rerender": false,
  "output": { "video_url": "/api/v1/media/clips/55/video", "srt_url": "/api/v1/media/clips/55/srt", "rendered_at": "…" }
}
```
`regions.source`: `clip` (override) → `channel` (default Kanal) → `stream` (hasil deteksi), urutan prioritas region efektif.

### `PATCH /api/v1/clips/{id}`: edit Klip
- **FR:** FR-015, FR-016, FR-017 · **Idempoten:** ya (set nilai)
- **Request** (semua field opsional):
```json
{
  "start_ms": 3602000, "end_ms": 3654500,
  "layout_preset_id": 3, "subtitle_style_id": 2, "subtitle_language": "id",
  "title": "Jumpscare paling brutal",
  "subtitle_overrides": { "words": { "128834": "gue" }, "line_breaks_after_word_ids": [128836] },
  "translated_lines": [{ "start_ms": 3601200, "end_ms": 3603900, "text": "Gila, dia beneran lompat!" }]
}
```
- **Aturan:** status `rendering` → 409. Status `rendered`/`render_failed` → setelah edit menjadi `approved` (`needs_rerender = true`). Jika Klip `approved` dan durasi baru di luar 15–90 detik → 400 (BR-004). `subtitle_language = id` ditolak jika `detected_language = id`. `word_highlight` + `subtitle_language = id` → gaya dipaksa mode `sentence` saat render (BR-008), respons memuat `"warnings": ["Terjemahan memakai mode kalimat"]`.
- **Response 200:** objek Klip seperti `GET /clips/{id}`.
- **Error:** 400 `VALIDATION_ERROR`; 409 `INVALID_STATE`, `SOURCE_DELETED`.

### `POST /api/v1/clips/{id}/approve` · `/reject` · `/restore` · `/unapprove`
- **FR:** FR-014 · **Idempoten:** ya jika status sudah target (200 tanpa perubahan)
- Transisi sesuai 03-user-flow.md 4.3. `approve` dari `candidate` saja; `reject` dari `candidate`/`approved`; `restore` dari `rejected`; `unapprove` dari `approved`.
- **Response 200:** `{ "id": 55, "status": "approved" }`
- **Error:** 400 `VALIDATION_ERROR` (approve dengan durasi di luar 15–90 detik, `fields.duration_ms`); 409 `INVALID_STATE`.

### `POST /api/v1/clips/{id}/snap`
- **Request:** `{ "edge": "end", "position_ms": 3655000 }` · **Response 200:** `{ "snapped_ms": 3654500, "segment_id": 884 }` (batas Segmen Transkrip terdekat ±2 detik; tanpa kandidat → `snapped_ms = position_ms`).

### `PUT /api/v1/clips/{id}/regions`
- **FR:** FR-008, FR-015
- **Request:**
```json
{ "regions": [{ "role": "cam", "x": 0.73, "y": 0.69, "w": 0.25, "h": 0.28 },
              { "role": "content", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0 }],
  "save_as_channel_default": true,
  "apply_to_stream_clips": true }
```
- **Perilaku:** menyimpan override Klip (replace per role). `save_as_channel_default` → upsert `cam_regions` milik Kanal + `channels.default_layout_preset_id` = preset Klip; Stream Sumber tanpa Kanal → 409 `INVALID_STATE` ("Pilih Kanal dulu"). `apply_to_stream_clips` → hapus override Klip lain di stream yang statusnya `candidate`/`approved` agar memakai default baru.
- **Response 200:** `{ "clip_id": 55, "regions_source": "clip", "affected_clip_ids": [56, 58, 61] }`
- **Error:** 400 (koordinat di luar 0–1, w/h < 0,05, role tidak sesuai preset).

### `GET /api/v1/clips/{id}/subtitles`
- **Response 200:**
```json
{ "language": "source", "mode": "word_highlight",
  "lines": [{ "start_ms": 3601200, "end_ms": 3602100,
              "words": [{ "word_id": 128830, "text": "Dude", "start_ms": 3601200, "end_ms": 3601450 }] }] }
```
Untuk `language = id` (`mode = sentence`), `words` kosong dan setiap baris punya `text`.

### `POST /api/v1/clips/{id}/translate`
- **FR:** FR-016 · Dijalankan sinkron (Klip ≤ 90 detik, timeout 45 detik). Hasil disimpan ke `clips.translated_lines`; `force=true` menerjemahkan ulang walau cache ada.
- **Request:** `{ "target": "id", "force": false }` · **Response 200:** `{ "translated_lines": [ … ] }`
- **Error:** 409 `INVALID_STATE` (bahasa sumber sudah `id`), `SECRET_MISSING`; 502 `UPSTREAM_ERROR` setelah 2 percobaan (UI mengembalikan Bahasa Tampil ke `source`).

### `POST /api/v1/clips/{id}/preview-render`
- **Request:** `{ "at_ms": 3610000 }` (5 detik mulai `at_ms`, dibatasi dalam rentang Klip) · **Response 202:** `{ "job": { "id": 300, "job_type": "render", "purpose": "preview", "preview_at_ms": 3610000, "is_heavy": false } }`. Hasil di `/media/clips/{id}/preview`. Tidak mengubah status Klip; boleh untuk Klip berstatus apa pun kecuali `rendering`. Pratinjau baru menimpa yang lama; Job pratinjau sebelumnya yang masih `queued` dibatalkan.
- **Error:** 409 `SOURCE_DELETED`.

### `POST /api/v1/clips/{id}/render`
- **FR:** FR-018 · **Idempoten:** ya. Jika sudah ada Job `render` `queued`/`running` untuk Klip ini, kembalikan Job itu (200), bukan membuat baru.
- **Request:** body kosong.
- **Response 202:** `{ "clip": { "id": 55, "status": "rendering" }, "job": { "id": 301, "job_type": "render", "status": "queued" } }`
- **Error:** 409 `INVALID_STATE` (status bukan `approved`/`render_failed`, pesan "Setujui klip dulu sebelum render."), `SOURCE_DELETED`.

### `POST /api/v1/streams/{id}/clips/render-approved`
- **Response 202:** `{ "jobs": [{ "clip_id": 55, "job_id": 301 }], "skipped": [{ "clip_id": 60, "reason": "SOURCE_DELETED" }] }`

### `GET /api/v1/jobs?status=queued,running&source_stream_id=12&limit=50`
- **Response 200:** `{ "items": [{ "id": 101, "job_type": "transcribe", "status": "running", "progress_pct": 35, "stage": "Mengirim audio 7/20", "source_stream_id": 12, "clip_id": null, "awaiting_confirmation": false, "error_message": null, "started_at": "…" }], "total": 3 }`

### `POST /api/v1/jobs/{id}/cancel`
- Status `queued`/`running` → `cancelled` (Worker menghentikan subprocess ≤ 10 detik). Pada `record_live`, cancel = sama dengan `stop`. · **Response 200:** objek Job · **Error:** 409 jika sudah selesai.

### `POST /api/v1/jobs/{id}/retry`
- Hanya Job `failed`/`cancelled`. Membuat Job baru (`retry_of_job_id = id`) dengan `checkpoint` disalin. · **Response 202:** `{ "job": { "id": 145, "retry_of_job_id": 101, "status": "queued" } }` · **Error:** 409 `INVALID_STATE`, `SOURCE_DELETED`.

### `POST /api/v1/jobs/{id}/confirm`
- **FR:** FR-022 · Untuk Job `transcribe` dengan `awaiting_confirmation = true`.
- **GET sebelumnya** (`GET /jobs/{id}`) memuat `"usage_estimate": { "audio_ms": 7800000, "estimated_llm_windows": 260, "pricing_links": { "transcriber": "https://…", "llm": "https://…" } }`.
- **Request:** `{ "proceed": true, "range": null }` atau `{ "proceed": true, "range": { "start_ms": 0, "end_ms": 3600000 } }` (proses sebagian saja jika melebihi batas). `proceed: false` → Job tetap tertahan.
- **Response 200:** objek Job (`awaiting_confirmation: false`).

### `POST /api/v1/system/open-folder`
- **FR:** FR-018, FR-025 · Membuka file explorer OS (Explorer/Finder) di komputer lokal. **Request:** `{ "target": "output" }` atau `{ "target": "clip", "clip_id": 55 }` (membuka folder output dengan file Klip terpilih) atau `{ "target": "stream", "stream_id": 12 }`. Path dibangun dari ID/pengaturan, bukan dari input bebas.
- **Response 200:** `{ "opened": true }` · **Error:** 404 (Klip belum dirender / folder tidak ada).

### `GET /api/v1/settings` · `PATCH /api/v1/settings`
- **FR:** FR-021 · **Response GET 200:**
```json
{
  "score_weights": { "audio": 0.3, "chat": 0.2, "llm": 0.5 },
  "score_min_threshold": 40, "chat_delay_ms": 8000, "chat_reaction_words": ["wkwk", "kekw"],
  "live_segment_seconds": 10, "live_block_minutes": 5, "live_last_n_default_s": 60,
  "max_heavy_jobs": 1, "confirm_usage_over_min": 30, "max_audio_minutes_per_job": 600,
  "transcriber_provider": "deepgram", "llm_provider": "anthropic",
  "llm_models": { "judge_highlight": null, "translate_lines": null, "write_captions": null },
  "kick_live_chat_enabled": false,
  "upload_default_mode": "manual", "upload_platforms_enabled": ["youtube", "tiktok", "instagram", "facebook"],
  "caption_templates": { "youtube": "", "tiktok": "", "instagram": "", "facebook": "" },
  "manual_upload_urls": { "youtube": "https://studio.youtube.com", "tiktok": "https://www.tiktok.com/upload", "instagram": "https://www.instagram.com", "facebook": "https://business.facebook.com" },
  "default_subtitle_style": "Highlight Kata", "output_dir": "C:\\Users\\nama\\Klipin\\output", "download_max_height": 1080,
  "secrets": { "transcriber_api_key": { "set": true, "masked": "…a1b2" }, "llm_api_key": { "set": false, "masked": null } },
  "storage": { "keyring_available": true }
}
```
- **PATCH request:** subset field di atas (kecuali `secrets`, `storage`). Validasi sesuai 02-requirements.md bagian 3; total bobot ≠ 1,00 → 400 `VALIDATION_ERROR`.

### `PUT /api/v1/secrets/{name}` · `DELETE` · `POST /test`
- `name`: `transcriber_api_key`, `llm_api_key`.
- **PUT request:** `{ "value": "…" }` → disimpan di keyring, nilai tidak pernah dikembalikan. **Response 200:** `{ "name": "llm_api_key", "set": true, "masked": "…9f3c" }`
- **POST /test response 200:** `{ "ok": true, "provider": "anthropic", "latency_ms": 820 }` atau `{ "ok": false, "error": "401 invalid x-api-key" }` (pesan penyedia diringkas, tanpa key). Timeout 10 detik.

### `GET /api/v1/upload-accounts`
- **FR:** FR-019 · Status keempat Platform Tujuan, termasuk yang belum dikonfigurasi.
- **Response 200:**
```json
{ "platforms": [
  { "platform": "youtube",   "configured": true,  "account": { "id": 1, "display_name": "NamaKanal", "account_status": "connected", "token_expires_at": null },
    "limits": { "max_duration_s": 180, "caption_max": 5000, "title_max": 100, "visibility_options": ["private"], "forced_private_reason": "Project API belum diaudit YouTube" } },
  { "platform": "tiktok",    "configured": true,  "account": null, "limits": null },
  { "platform": "instagram", "configured": false, "account": null, "limits": null, "setup_hint": "Isi META_APP_ID & META_APP_SECRET (lihat panduan)" },
  { "platform": "facebook",  "configured": false, "account": null, "limits": null, "setup_hint": "Isi META_APP_ID & META_APP_SECRET (lihat panduan)" } ] }
```
`limits` berasal dari `Publisher.limits()` (07-integrasi.md); untuk TikTok, nilai `visibility_options` & `max_duration_s` diambil dari API info kreator dan di-cache 1 jam.

### `GET /api/v1/oauth/{platform}/start`
- **FR:** FR-019 · `platform` ∈ `youtube`, `tiktok`, `instagram`, `facebook`. Membuat `state` acak (+ PKCE `code_verifier` bila platform mendukung), disimpan di memori server 10 menit bersama `platform`, lalu `302` ke layar persetujuan penyedia dengan redirect URI `{KLIPIN_OAUTH_REDIRECT_BASE}/oauth/callback/{platform}` (default `http://localhost:8765/oauth/callback/{platform}`). Scope sesuai 07-integrasi.md.
- **Error:** 409 `PLATFORM_NOT_CONFIGURED` (kredensial aplikasi developer platform kosong).

### `GET /oauth/callback/{platform}?code=…&state=…`
- Berada di root, bukan di `/api/v1` (redirect URI didaftarkan apa adanya di konsol developer). Tidak memakai `X-Klipin-Token`, tetapi `state` wajib cocok, sekali pakai, dan `platform` sama dengan saat start.
- Menukar `code` → token, menyimpan token ke keyring, mengambil identitas akun, lalu:
  - `youtube`/`tiktok`: upsert `upload_accounts` (`connected`) → `302` ke `/#/settings?tab=accounts&connected={platform}`.
  - `facebook`: simpan token sementara di memori (10 menit), `302` ke `/#/settings?tab=accounts&select_page=1` untuk memilih Halaman.
  - `instagram`: cari akun Instagram Professional yang terhubung; satu → langsung disimpan (`target_id` = IG user ID); lebih dari satu → `302` ke `...&select_ig=1`; tidak ada → `302` ke `...&error=no_ig_professional`.
- `error=access_denied` → `302` ke `/#/settings?tab=accounts&error=cancelled`. `state` tidak valid → halaman error sederhana 400.

### `GET /api/v1/oauth/{platform}/targets` · `POST /api/v1/oauth/{platform}/targets`
- **FR:** FR-019 · Hanya `facebook` (Halaman) dan `instagram` (akun Professional) setelah callback, selama token sementara masih ada.
- **GET Response 200:** `{ "targets": [{ "id": "1029384756", "name": "Halaman Klip Horor" }, { "id": "5647382910", "name": "Halaman Lain" }] }`
- **POST Request:** `{ "target_id": "1029384756" }` → upsert `upload_accounts` (`target_id`, `display_name` = nama Halaman/akun) · **Response 201:** objek Akun Unggah.
- **Error:** 409 `INVALID_STATE` (token sementara kedaluwarsa, ulangi Hubungkan); 400 (`target_id` tidak ada di daftar).

### `DELETE /api/v1/upload-accounts/{id}`
- Mencabut token di platform bila tersedia endpoint pencabutan, menghapus entri keyring, lalu `account_status = disconnected` (record dipertahankan jika punya riwayat Unggahan; selain itu dihapus). · **Response 200:** `{ "disconnected": true }`

### `GET /api/v1/clips/{id}/upload-dialog`
- **FR:** FR-020, FR-025, FR-027 · Data untuk membuka dialog unggah dalam satu panggilan.
- **Response 200:**
```json
{
  "clip": { "id": 55, "status": "rendered", "duration_ms": 54000, "file_bytes": 48234496, "subtitle_language": "source" },
  "platforms": [
    { "platform": "youtube", "existing_upload": null, "auto_available": true,  "auto_blockers": [], "visibility_options": ["private"], "forced_private": true },
    { "platform": "tiktok",  "existing_upload": { "id": 9, "mode": "manual", "status": "pending" }, "auto_available": false, "auto_blockers": ["ACCOUNT_NOT_CONNECTED"] },
    { "platform": "instagram", "existing_upload": null, "auto_available": false, "auto_blockers": ["PLATFORM_NOT_CONFIGURED"] },
    { "platform": "facebook",  "existing_upload": null, "auto_available": false, "auto_blockers": ["PLATFORM_NOT_CONFIGURED"] } ],
  "caption_drafts": { "youtube": { "title": "…", "caption": "…", "hashtags": ["#shorts"], "edited": false } },
  "default_mode": "manual"
}
```
`auto_blockers` ∈ `ACCOUNT_NOT_CONNECTED`, `ACCOUNT_NEEDS_REAUTH`, `PLATFORM_NOT_CONFIGURED`, `DURATION_EXCEEDS_LIMIT`, `FILE_TOO_LARGE` (BR-013). Platform dengan `existing_upload` aktif/berhasil tidak bisa dipilih (BR-009).
- **Error:** 409 `INVALID_STATE` (Klip bukan `rendered`, pesan "Render klip dulu.").

### `POST /api/v1/clips/{id}/captions` · `PATCH /api/v1/clips/{id}/captions`
- **FR:** FR-027
- **POST** (buat/ulang draf via LLM, sinkron, timeout 30 detik) · **Request:** `{ "platforms": ["youtube", "tiktok"], "force": false }`. Draf yang `edited: true` tidak ditimpa kecuali `force: true`. **Response 200:** `{ "caption_drafts": { … } }`. LLM gagal / key kosong → 200 dengan draf template default + `"warning": "Draf otomatis tidak tersedia."`
- **PATCH** (simpan edit Pengguna) · **Request:** `{ "tiktok": { "caption": "POV: jumpscare jam 3 pagi 😭", "hashtags": ["#fyp", "#horor"] } }` → disimpan dengan `edited: true`. **Response 200:** `{ "caption_drafts": { … } }`
- Template tetap per platform (`settings.caption_templates`) ditambahkan saat Unggahan dibuat, bukan di draf.

### `POST /api/v1/clips/{id}/uploads`
- **FR:** FR-020, FR-025 · **Idempoten:** dijaga BR-009 (index unik parsial per `clip_id, platform`). Semua item divalidasi dulu; jika satu item gagal validasi, tidak ada Unggahan yang dibuat (all-or-nothing).
- **Request:**
```json
{ "items": [
  { "platform": "tiktok",  "mode": "manual", "caption": "POV: jumpscare jam 3 pagi 😭", "hashtags": ["#fyp", "#horor"] },
  { "platform": "youtube", "mode": "auto", "title": "Jumpscare paling brutal", "caption": "Klip dari stream NamaStreamer", "hashtags": ["#shorts"], "visibility": "private" } ] }
```
- **Response 201:**
```json
{ "uploads": [
  { "id": 10, "platform": "tiktok", "mode": "manual", "status": "pending",
    "package": { "video_url": "/api/v1/media/clips/55/video?download=1", "srt_url": "/api/v1/media/clips/55/srt",
                 "caption_full": "POV: jumpscare jam 3 pagi 😭\n\n#fyp #horor", "upload_page_url": "https://www.tiktok.com/upload",
                 "output_folder": "C:\\Users\\nama\\Klipin\\output" } },
  { "id": 11, "platform": "youtube", "mode": "auto", "status": "pending", "job": { "id": 320, "job_type": "upload", "is_heavy": false } } ] }
```
`upload_page_url` = halaman upload resmi platform (daftar di 07-integrasi.md), dibuka UI di tab baru.
- **Error:** 400 `VALIDATION_ERROR` (judul YouTube 1–100, caption melebihi batas platform, hashtag tidak valid, `visibility` di luar `visibility_options`; `fields` memakai path `items[1].title`); 409 `INVALID_STATE` (Klip bukan `rendered`), `DUPLICATE_UPLOAD` ("Klip ini sudah/sedang diunggah ke {Platform}."), `AUTO_NOT_AVAILABLE` (mode `auto` dengan `auto_blockers`, BR-013).

### `GET /api/v1/clips/{id}/uploads`
- Riwayat Unggahan Klip (semua platform & mode), termasuk `package` untuk Unggahan manual `pending`.

### `POST /api/v1/uploads/{id}/mark-posted`
- **FR:** FR-026 · Hanya `mode = manual` & `status = pending`. **Idempoten:** ya (sudah `uploaded` → 200 tanpa perubahan).
- **Request:** `{ "external_url": "https://www.tiktok.com/@akun/video/7311111111111111111" }` (`external_url` opsional / `null`).
- **Response 200:** `{ "id": 10, "status": "uploaded", "external_url": "…", "uploaded_at": "…" }`
- **Error:** 400 `VALIDATION_ERROR` ("URL tidak sesuai platform TikTok."); 409 `INVALID_STATE` (bukan manual/pending).

### `DELETE /api/v1/uploads/{id}`
- **FR:** FR-026 · Membatalkan Unggahan manual `pending` (record dihapus), atau menghapus Unggahan dari riwayat (status `uploaded`/`failed`) agar Klip bisa diposting ulang ke platform itu (BR-014). Tidak menghapus postingan di platform. `?confirm=true` wajib untuk status `uploaded`.
- **Response 200:** `{ "deleted": true }` · **Error:** 409 `INVALID_STATE` (Unggahan `auto` yang sedang `pending`/`uploading`: batalkan Job-nya dulu).

### `POST /api/v1/uploads/{id}/retry` · `POST /api/v1/uploads/{id}/switch-manual`
- **FR:** FR-020 · Hanya Unggahan `auto` berstatus `failed`.
- `retry` → Unggahan baru `auto` (`pending`) + Job `upload`, menyalin teks; `switch-manual` → Unggahan baru `manual` (`pending`) + `package`. Unggahan lama tetap di riwayat sebagai `failed`.
- **Response 201:** objek Unggahan baru · **Error:** 409 `INVALID_STATE`, `AUTO_NOT_AVAILABLE` (retry saat akun bermasalah).

### `GET /api/v1/events?t={token}`: Server-Sent Events
- **FR:** FR-023 · `Content-Type: text/event-stream`; heartbeat komentar `: ping` setiap 15 detik. Klien menyambung ulang otomatis (EventSource) dan memuat ulang data via REST saat tersambung kembali.
- Server membaca perubahan dari tabel `jobs`/entitas (polling DB internal tiap 1 detik), memenuhi NFR "UI terbarui ≤ 3 detik".
- **Jenis event:**
| `event` | `data` contoh | Dipicu oleh |
|---|---|---|
| `job.updated` | `{"id":101,"job_type":"transcribe","status":"running","progress_pct":40,"stage":"Mengirim audio 8/20","source_stream_id":12}` | Progres/status Job |
| `stream.updated` | `{"id":12,"status":"ready","clip_counts":{"candidate":12}}` | Status Stream Sumber |
| `clip.created` | `{"id":77,"source_stream_id":17,"origin":"live_marker","status":"candidate"}` | Kandidat Klip baru (termasuk saat live) |
| `clip.updated` | `{"id":55,"status":"rendered"}` | Status Klip |
| `upload.updated` | `{"id":11,"clip_id":55,"platform":"youtube","mode":"auto","status":"uploaded","external_url":"https://youtu.be/…","posted_as_private":true}` | Status Unggahan |
| `live.position` | `{"stream_id":17,"recorded_ms":1203000,"gap":false}` | Tiap segmen live baru |

### `GET /api/v1/media/...`
- Semua mendukung `Range` (206) dan `?t={token}`. Path dibangun dari ID di DB, **bukan** dari input path, untuk mencegah path traversal.
- `frame?t_ms=3610000&w=640` → JPEG (FFmpeg seek), cache 60 detik.
- `live.m3u8` → playlist HLS event berisi segmen yang sudah tersimpan; `#EXT-X-ENDLIST` ditambahkan setelah rekaman berhenti.
- `clips/{id}/video?download=1` → `Content-Disposition: attachment; filename="{nama file render}"`.
- 409 `SOURCE_DELETED` untuk `/source` dan `/frame` jika video sumber dihapus.

## 4. Webhook
Tidak berlaku: tidak ada layanan luar yang memanggil Klipin selain redirect OAuth (`/oauth/callback/{platform}`). Status publikasi asinkron TikTok/Instagram/Facebook diperiksa dengan polling dari Worker, bukan webhook. Penyedia transkripsi dipanggil secara sinkron per potongan, bukan dengan callback, karena Klipin tidak punya URL publik.

## 5. Rate Limit & Batas Ukuran
| Item | Batas | Alasan |
|---|---|---|
| Ukuran body JSON | 1 MB | Tidak ada unggah file lewat API (file lokal dirujuk lewat path) |
| `POST /streams/inspect` | Maks. 1 request berjalan sekaligus | yt-dlp berat; request berikutnya menunggu |
| `POST /clips/{id}/translate` | Timeout 45 detik | Klip ≤ 90 detik |
| `POST /secrets/{name}/test` | Timeout 10 detik | |
| `GET /streams/{id}/transcript` | Rentang ≤ 30 menit | Respons tetap < 2 MB |
| `GET /media/.../frame` | `w` ≤ 1280 | |
| Koneksi SSE | Maks. 5 per server | Hanya tab lokal Pengguna |
| Rate limit umum | Tidak berlaku | Hanya satu Pengguna lokal; perlindungan biaya API ada di FR-022 & BR-003 |

## Keputusan implementasi (disetujui pemilik 2026-11-21)
Keputusan yang diambil saat implementasi karena spesifikasi belum merinci; nomor K-xx sama dengan riwayat di `docs/CATATAN-SESI.md`.

- **K-3** Koneksi SSE ke-6 ditolak `429` dengan kode baru `TOO_MANY_CONNECTIONS` (belum ada di tabel error 06-api.md §1) _(kode: `api/routes/events.py`)_
- **K-6** Respons Job memuat `stream_title` (untuk kolom "Objek" P-06); event SSE `job.updated` memuat `started_at`/`finished_at` _(kode: `api/routes/jobs.py`, `api/routes/events.py`)_
- **K-7** `GET /system/health` = cek `klipin doctor` tanpa cek port (port dipakai server itu sendiri); respons `{ok, checks[], home, backup_dir}` _(kode: `api/routes/system.py`)_
- **K-9** Validasi PATCH /settings untuk kunci yang tidak punya aturan di 02-requirements.md §3: `score_min_threshold` 0–100, `live_last_n_default_s` 15–90, enum penyedia, `default_subtitle_style` harus ada di DB, kunci asing ditolak _(kode: `api/schemas/settings.py`)_
- **K-13** Bentuk respons `GET /streams` (tidak dirinci di 06-api.md): item = `id, title, platform, source_type, status, duration_ms, error_message, created_at, channel_id, channel{id,name}, storage, clip_counts`; `clip_counts` memuat keenam status Klip. Detail menambah `source_url`, `detected_language`, `has_chat`, `suggested_layout_preset`, `active_jobs` (+ `stage`, `awaiting_confirmation`). `POST /streams` 201 memakai item yang sama untuk `stream` _(kode: `api/schemas/streams.py`)_
- **K-14** Nilai `fields` error dikirim sebagai string (`required_bytes`, `free_bytes`, `existing_stream_id`), mengikuti tipe `fields` yang ada. Pesan duplikat: "Video ini sudah pernah diimpor." (tidak ada di 08-ui-ux §7). Timeout inspect 10 dtk → 502 `UPSTREAM_ERROR` "yt-dlp tidak menjawab dalam 10 detik. Coba lagi." _(kode: `streams.py`)_
- **K-25** FR-022: `transcribe` ditahan bila durasi > ambang konfirmasi **atau** > `max_audio_minutes_per_job` (batas berlaku walau konfirmasi mati); durasi tak diketahui → tidak ditahan. Perkiraan jendela LLM = round(jam × 120) (batas BR-003; cocok dengan contoh 06-api 2 j 10 m → 260), minimal 1. `usage_estimate` menambah `duration_ms`, `max_audio_ms`, `over_limit` (usul tambah ke 06-api.md). Rentang konfirmasi disimpan di `checkpoint.range` (bukan `scope_*`) agar Job tetap dianggap seluruh stream dan lanjut ke `score_highlights`; validasi: di dalam durasi, selesai > mulai, panjang ≤ batas. Konfirmasi tanpa rentang saat melebihi batas → 409. Setelah unduh, `duration_ms` diperbarui dari FFprobe file asli. GET /settings memuat `pricing_links`. P-04 menampilkan banner + dialog konfirmasi yang sama dengan P-06 _(kode: `usage.py`, `jobs.confirm_job`, `pipeline.on_success`, `handlers/download.py`, `components/UsageConfirmDialog.tsx`)_
- **K-29** Bentuk respons yang tidak dirinci di 06-api.md: `GET /layout-presets` → `{items:[{id,code,name,is_builtin,params}]}`; `GET /channels` → `{items:[{id,platform,external_id,name,default_layout_preset,default_regions,stream_count}],total}`; `POST /channels` hanya membuat Kanal `local` (nama 1–200, nama sama tanpa beda huruf → 409 + `existing_channel_id`); `PATCH /streams/{id}/channel` `{channel_id}` → `{stream}` (Kanal platform apa pun boleh); `GET /streams/{id}/regions` → `{stream_id, detected, suggested_layout_preset, regions, channel, message}` dengan `message` = teks FR-006 bila deteksi selesai, saran `center_crop`, tanpa region. `PUT /clips/{id}/regions`: replace per role; role harus milik preset (`gaming`/`custom`: cam, content; `split_two`/`podcast`: face_a, face_b; `irl`/`center_crop`: tidak ada) dan override gabungan harus lengkap (custom: 1–2 region); Klip `rendering` → 409; `rendered`/`render_failed` → `approved`; `apply_to_stream_clips` hanya Klip `candidate`/`approved` lain. Urutan tumpukan `custom` = urutan role (cam di atas) karena tabel tidak punya kolom urutan. `GET /media/streams/{id}/frame`: `w` 16–1280 (default 640), `t_ms` > durasi → 400, video belum ada → 409 `INVALID_STATE`, cache lewat `Cache-Control: private, max-age=60` _(kode: `layouts.py`, `api/routes/layouts.py`, `api/routes/media.py`)_
- **K-35** Endpoint Klip (`clips.py`): daftar memuat `duration_ms`, `needs_rerender`, `uploads`; skor null diurut terakhir. Detail memuat `subtitle_overrides`, `translated_lines`, `render_error`, `score_breakdown.llm` 0–100. `needs_rerender` = ada file render tetapi status bukan `rendered`. PATCH: `start_ms/end_ms/preset/gaya/bahasa` tidak boleh null; durasi dicek 15–90 hanya untuk Klip approved/rendered/render_failed; `subtitle_language=id` ditolak 400 bila bahasa stream `id` atau belum diketahui; ubah rentang saat video sumber dihapus → 409 `SOURCE_DELETED`. Klip manual: judul default `"{Kanal} - mm:ss"`, tanpa batas durasi saat dibuat (dicek saat approve). Snap: ±2 dtk, `start` ke awal segmen, `end` ke akhir segmen. Timeline: ember = nilai tertinggi jendela yang beririsan, LLM 0–1. Waveform: PCM 8 kHz, cache `streams/{id}/cache/`. Bagian render TC-031 (`.srt`/frame berisi "gue") diuji di T-043/T-046 _(kode: `clips.py`, `api/routes/clips.py`, `media/waveform.py`)_

## Asumsi & Pertanyaan Terbuka
- [ASUMSI] Pemilihan file lokal memakai penjelajah folder bawaan Klipin (`/fs/list`) karena browser tidak memberi path asli dari `<input type=file>`, dan menyalin file berukuran GB lewat HTTP tidak efisien.
- [ASUMSI] SSE dibangun dengan polling DB internal 1 detik (bukan notifikasi antar-proses) karena API dan Worker adalah proses terpisah; cukup untuk satu Pengguna.
- [ASUMSI] Penerjemahan Klip dikerjakan sinkron karena teks pendek; jika penyedia lambat, bisa dipindah menjadi Job ringan.
- [ASUMSI] OAuth memakai client tipe Desktop + PKCE dengan redirect loopback `127.0.0.1`.
- [TANYA] Apakah perlu endpoint ekspor/impor Preset Layout & Gaya Subtitle (file JSON) untuk dipindah ke komputer lain? (Pengguna)

## Riwayat Perubahan
| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.3 | 2026-11-21 | Keputusan implementasi disetujui pemilik (K-3, K-6, K-7, K-9, K-13, K-14, K-25, K-29, K-35): bentuk respons yang belum dirinci (streams, channels, regions, klip, usage_estimate, system/health), kode `TOO_MANY_CONNECTIONS`, validasi Pengaturan, aturan PATCH Klip |
| 1.0 | 2026-11-20 | Draf awal |
| 1.2 | 2026-11-20 | Hasil CEK #1, #2, #7, #10: render pratinjau memakai `purpose = preview`; endpoint `POST /system/open-folder`; `GET /streams/{id}/waveform`; respons Pengaturan memuat semua kunci di 05-database.md; base URL localhost |
| 1.1 | 2026-11-20 | Menyesuaikan unggah multi-platform & Mode Unggah (01-prd.md v1.1): OAuth per platform (`/oauth/{platform}/start`, `/oauth/callback/{platform}`, pilih Halaman/akun IG), `upload-dialog`, draf caption, `POST /clips/{id}/uploads` multi-platform manual/otomatis, `mark-posted`, hapus/retry/switch-manual Unggahan; kode error baru; event SSE; callback diseragamkan di luar `/api/v1` |
