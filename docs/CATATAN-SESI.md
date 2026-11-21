# Catatan Sesi: status kerja & keputusan di luar spesifikasi

Dibaca agent sebelum melanjutkan task di device mana pun. Riwayat percakapan dan memori agent
tidak ikut ter-clone, jadi semua yang penting dicatat di sini. Spesifikasi di `docs/spec/`
tetap sumber kebenaran; file ini hanya mencatat hal yang belum (atau tidak) masuk ke sana.

Terakhir diperbarui: 2026-11-21, setelah T-036.

## Posisi kerja

- Fase 0 (T-001–T-007) dan Fase 1 (T-008–T-020) selesai; Checkpoint 0 & 1 lulus.
- Fase 2 dimulai atas permintaan pemilik (2026-11-21). T-021–T-036 selesai; task berikutnya: **T-037** (`highlight_windows` + pra-seleksi BR-003).
- Satu commit per task, format `T-0xx: ringkasan`. CI GitHub Actions (ubuntu + windows) wajib hijau.
- Tes: `KLIPIN_PROVIDERS=fake uv run pytest` (358 tes setelah T-036); frontend `pnpm lint && pnpm build`.

## Keputusan di luar spesifikasi

Status **menunggu**: belum disetujui pemilik; jangan diubah tanpa bertanya, dan setelah
disetujui pindahkan ke dokumen spesifikasi terkait (naikkan versi + baris Riwayat Perubahan).

| # | Keputusan | Di mana | Status |
|---|---|---|---|
| 1 | Palet & font 08-ui-ux.md §5 (ungu `#7C5CFF`, latar `#0F1115`, Inter) **dipertahankan** walau antislop menandainya | `frontend/src/styles/index.css` | Disetujui pemilik |
| 2 | Membatalkan Job pipeline (download/transcribe/detect_layout/score_highlights seluruh stream) membuat Stream Sumber `failed` dengan pesan "Job dibatalkan." State machine §4.1 tidak mengatur ini; tanpanya stream tertahan di `downloading`/`processing` | `backend/klipin/jobs.py` (`cancel_job`) | Menunggu |
| 3 | Koneksi SSE ke-6 ditolak `429` dengan kode baru `TOO_MANY_CONNECTIONS` (belum ada di tabel error 06-api.md §1) | `api/routes/events.py` | Menunggu, usul tambah ke 06-api.md |
| 4 | Env yang diisi eksplisit menang atas Pengaturan: `KLIPIN_MAX_HEAVY_JOBS` vs `settings.max_heavy_jobs` | `worker/loop.py` (`max_heavy_jobs`) | Menunggu |
| 5 | Pengaturan `transcriber_provider`/`llm_provider` menang atas env `KLIPIN_TRANSCRIBER`/`KLIPIN_LLM_PROVIDER`; env hanya cadangan bila Pengaturan kosong. Dipindah ke 04-arsitektur.md v1.3 §8.2 | `providers/transcriber/__init__.py` (`provider_name`) | Disetujui pemilik (2026-11-21) |
| 6 | Respons Job memuat `stream_title` (untuk kolom "Objek" P-06); event SSE `job.updated` memuat `started_at`/`finished_at` | `api/routes/jobs.py`, `api/routes/events.py` | Menunggu, usul tambah ke 06-api.md |
| 7 | `GET /system/health` = cek `klipin doctor` tanpa cek port (port dipakai server itu sendiri); respons `{ok, checks[], home, backup_dir}` | `api/routes/system.py` | Menunggu (skema tidak dirinci di spesifikasi) |
| 8 | `update-ytdlp` = `uv lock --upgrade-package yt-dlp` lalu `uv sync --no-install-project --inexact`; mengubah `uv.lock`. Di mode `fake` hanya simulasi | `backend/klipin/system.py` | Menunggu |
| 9 | Validasi PATCH /settings untuk kunci yang tidak punya aturan di 02-requirements.md §3: `score_min_threshold` 0–100, `live_last_n_default_s` 15–90, enum penyedia, `default_subtitle_style` harus ada di DB, kunci asing ditolak | `api/schemas/settings.py` | Menunggu |
| 10 | Fixture audio "tenang" = hening digital (nada pelan membuat FLAC > 6 MB); fixture wajah dari 2 video domain publik Wikimedia Commons | `tests/fixtures/README.md` | Disetujui (sumber CC0/PD dipilih pemilik) |
| 11 | `media/ytdlp.py`: URL disaring dulu per host (youtube.com, www/m/music.youtube.com, youtu.be, kick.com, www.kick.com) sebelum yt-dlp dipanggil, lalu hasilnya wajib `extractor_key` `Youtube`/`Kick`/`KickVOD` dan bukan playlist; selain itu `URL_NOT_SUPPORTED`. Hasil unduhan selalu di-remux ke MP4 (`FFmpegVideoRemuxer`) bila format tunggal bukan MP4 | `backend/klipin/media/ytdlp.py` | Menunggu |
| 12 | `estimated_size_bytes` = jumlah `filesize`/`filesize_approx` format terpilih (fallback `tbr` × durasi); `null` bila ada yang tak diketahui. Saat `null`, cek disk FR-001 **dilewati** (impor tetap jalan; disk penuh saat unduh ditangani Job) | `media/ytdlp.py`, `streams.py` (`check_disk`) | Menunggu |
| 13 | Bentuk respons `GET /streams` (tidak dirinci di 06-api.md): item = `id, title, platform, source_type, status, duration_ms, error_message, created_at, channel_id, channel{id,name}, storage, clip_counts`; `clip_counts` memuat keenam status Klip. Detail menambah `source_url`, `detected_language`, `has_chat`, `suggested_layout_preset`, `active_jobs` (+ `stage`, `awaiting_confirmation`). `POST /streams` 201 memakai item yang sama untuk `stream` | `api/schemas/streams.py` | Menunggu, usul tambah ke 06-api.md |
| 14 | Nilai `fields` error dikirim sebagai string (`required_bytes`, `free_bytes`, `existing_stream_id`), mengikuti tipe `fields` yang ada. Pesan duplikat: "Video ini sudah pernah diimpor." (tidak ada di 08-ui-ux §7). Timeout inspect 10 dtk → 502 `UPSTREAM_ERROR` "yt-dlp tidak menjawab dalam 10 detik. Coba lagi." | `streams.py` | Menunggu |
| 15 | Kata reaksi (FR-010): kata alfanumerik cocok sebagai kata utuh tanpa beda huruf besar/kecil (`lol` cocok di "lol bang", tidak di "lolos"; `wkwk` tidak cocok "wkwkwkwk"); emoji/simbol cocok sebagai potongan teks. Dihitung saat impor | `media/chat_replay.py` (`reaction_matcher`) | Menunggu |
| 16 | Jenis Pesan Chat: `liveChatTextMessageRenderer` → `text`; Paid Message/Sticker → `donation`; Membership + hadiah membership → `membership`; pesan sistem YouTube & ticker diabaikan (tidak disimpan). Chat tidak ada / gagal / VOD Kick → Pesan Chat lama dihapus dan `has_chat = 0` | `media/chat_replay.py`, `worker/handlers/download.py` | Menunggu |
| 17 | Job `download`: video 0–90%, chat 90–99%; checkpoint `video_done` + `video_path` (coba ulang tidak mengunduh ulang video utuh); chat replay diunduh terpisah setelah video agar kegagalannya tidak menggagalkan video; `video_width/height/fps` dari metadata yt-dlp (bisa kosong). Disk penuh → "Ruang disk habis. Kosongkan ruang lalu coba lagi." | `worker/handlers/download.py` | Menunggu |
| 18 | Mode `fake` memakai media fixture (`media/fake.py`), tanpa jaringan: semua URL YouTube/Kick sah dijawab dari `tests/fixtures/ytdlp/*.json` (ID dari URL, URL berisi "live" = live, durasi 30 dtk); Job `download` menyalin `gaming_facecam_30s.mp4` + `live_chat_spike.jsonl` ke `streams/{id}/` (±2 dtk progres simulasi) | `media/fake.py`, `streams.inspector`, `handlers/download.py` | Disetujui pemilik (2026-11-21), dipindah ke 04-arsitektur.md v1.3 §8.2 |
| 19 | P-01: tanpa thumbnail (inspect tidak mengembalikan frame); badge hanya "Kanal dikenal" (nama preset default menunggu `GET /channels`, T-034); tombol "Mulai Rekam Live" & "Pilih file dari komputer" belum ditampilkan (tanpa kontrol palsu) — URL live memberi teks penjelasan; banner izin yang ditutup diingat di `localStorage`. P-04 sementara berisi header stream + progres pipeline (`components/PipelineProgress.tsx`) sampai T-041 | `frontend/src/pages/P01Beranda.tsx`, `P04ReviewKlip.tsx` | Menunggu |
| 20 | P-02: filter status dikelompokkan Semua / Diproses (`queued,downloading,recording,processing`) / Siap direview / Gagal; 50 per halaman; kolom ukuran = total + rincian "Sumber · Render" (ukuran segmen live menyusul T-051); jumlah Klip hanya status yang > 0 | `frontend/src/pages/P02DaftarStream.tsx` | Menunggu |
| 21 | `Transcriber.transcribe(AudioChunk) → TranscriptionResult` (utterance + kata, waktu **relatif potongan**, label pembicara lokal); retry & penjahitan di handler (T-027). Error: `TranscriberAuthError` (pesan FR-005), `TranscriberTransientError` (429/5xx/timeout), `TranscriberBadAudioError` (400). API key dicek di factory **juga di mode fake** (TC-014): dev/E2E mode fake perlu isi API key sembarang. `FakeTranscriber`: naskah Indonesia tetap di kode (kalimat tiap 6 dtk absolut, kata tiap 1 dtk, pembicara "0"/"1", tiap kata ke-7 confidence 0,55), `silent_ranges`, kegagalan per indeks potongan | `providers/transcriber/` | Menunggu |
| 22 | Job `transcribe`: potongan i = [b_i, b_i + 10 mnt + 2 dtk] (b_i tiap 10 mnt dari awal rentang), audio FLAC mono 16 kHz diekstrak langsung per potongan (`ffmpeg -ss/-t`) ke `streams/{id}/audio/chunk_{start_ms}.flac`. "Batas potongan" untuk penjahitan = titik tengah zona tumpang tindih (b_i + 1 dtk), agar potongan kata di tepi audio tidak tercatat ganda. Label pembicara dicocokkan lewat kata sama (±300 ms) di zona tumpang tindih; tidak cocok → label baru (S3, …). Retry = 3 percobaan ulang (total 4 kiriman); semua error penyedia menandai potongan `failed`. Bahasa ditetapkan dari potongan pertama yang **berisi kata** (potongan hening tidak menetapkan bahasa) | `worker/handlers/transcribe.py` | Menunggu |
| 23 | Adapter Deepgram: `Content-Type: audio/flac` (contoh di dokumentasi hanya wav/mp3; FLAC tercantum sebagai `encoding` yang didukung, belum diuji ke API sungguhan); bahasa terdeteksi `en-US` dinormalkan ke `en`; tanpa `results.utterances` kata dikelompokkan per pembicara berurutan; 408/422 dianggap sementara; 402 → pesan "Kredit Deepgram habis…". Dependensi baru: `httpx` (runtime), `respx` (dev) | `providers/transcriber/deepgram.py` | Menunggu; uji ke API asli saat A/B T-061 (butuh izin biaya) |
| 24 | `Transcriber.transcribe(chunk, *, should_cancel=None)`: penyedia asinkron mengecek batal tiap ≤ 0,5 dtk (FR-023). AssemblyAI: `speech_models=["universal-2"]` eksplisit (dukungan `id` hanya terkonfirmasi di sana); transkrip + unggahan dihapus dari AssemblyAI setelah selesai/gagal/batal; status `error` → potongan `failed` (bukan retry); 403 diperlakukan seperti 401 sesuai INT-04 walau AssemblyAI juga memakai 403 untuk batas 20.000 request/5 menit; polling maks. 30 menit lalu dianggap sementara; wilayah US saja | `providers/transcriber/assemblyai.py` | Menunggu; uji ke API asli saat A/B T-061 |
| 25 | FR-022: `transcribe` ditahan bila durasi > ambang konfirmasi **atau** > `max_audio_minutes_per_job` (batas berlaku walau konfirmasi mati); durasi tak diketahui → tidak ditahan. Perkiraan jendela LLM = round(jam × 120) (batas BR-003; cocok dengan contoh 06-api 2 j 10 m → 260), minimal 1. `usage_estimate` menambah `duration_ms`, `max_audio_ms`, `over_limit` (usul tambah ke 06-api.md). Rentang konfirmasi disimpan di `checkpoint.range` (bukan `scope_*`) agar Job tetap dianggap seluruh stream dan lanjut ke `score_highlights`; validasi: di dalam durasi, selesai > mulai, panjang ≤ batas. Konfirmasi tanpa rentang saat melebihi batas → 409. Setelah unduh, `duration_ms` diperbarui dari FFprobe file asli. GET /settings memuat `pricing_links`. P-04 menampilkan banner + dialog konfirmasi yang sama dengan P-06 | `usage.py`, `jobs.confirm_job`, `pipeline.on_success`, `handlers/download.py`, `components/UsageConfirmDialog.tsx` | Menunggu |
| 26 | `detect_layout`: model BlazeFace + YuNet dibundel di `backend/klipin/layout/models/` (izin pemilik 2026-11-21; sumber, lisensi, SHA256 di README folder itu); per frame MediaPipe dulu, YuNet bila MediaPipe tidak menemukan wajah/gagal dimuat (tafsiran "fallback OpenCV DNN"). Sampel merata (lebar 960 px), minimal 10 untuk video pendek; frame dibaca dengan seek OpenCV, tanpa folder `frames/`. Ambang: tanpa wajah di ≥ 90% sampel → `center_crop`; ≥ 2 wajah di ≥ 50% sampel berwajah → `podcast` (bukan `split_two`) dengan `face_a`/`face_b` = wajah + 30%; satu wajah dengan sebaran pusat ≤ 8% dan luas < 25% → `gaming`; selain itu `irl` (tanpa region). Kotak `cam` = persegi panjang tepi panel yang **sisi terlemahnya** terkuat di peta gradien rata-rata antar-frame (cadangan: wajah + 40%); `content` = sisi frame di luar kolom cam bila lebarnya ≥ 50%, selain itu seluruh frame. Kanal dengan preset default: preset Kanal dipakai, region deteksi tetap disimpan untuk stream, kecocokan (IoU) dicatat di log Job. Pesan "Wajah tidak terdeteksi…" baru di log Job; tampil di UI pada T-041. Dependensi baru: `mediapipe` (membawa `opencv-contrib-python`), `numpy` | `layout/`, `worker/handlers/detect_layout.py` | Menunggu |
| 27 | Filtergraph preset statis (`media/ffmpeg.py`): tiap panel *cover* (region dipotong di tengahnya ke rasio panel lalu di-scale tepat, tanpa `pad`), panel ditumpuk `vstack`; offset & ukuran crop selalu genap (offset ganjil menggeser chroma yuv420p). `split_two` memakai `split_pct` (seed 50). `custom`: urutan tumpukan = urutan region yang diberikan, 1 region → penuh, 2 region → `top_pct` (default 50, belum ada di seed); penyimpanan urutan menyusul di T-034/T-042. Region wajib tidak ada → jatuh ke `center_crop` dengan alasan (`LayoutPlan.fallback_reason`) | `media/ffmpeg.py` | Menunggu |
| 28 | Jalur crop dinamis (`layout/crop_path.py`): jendela 9:16 setinggi frame; posisi per sampel 5 fps (dibaca berurutan dengan `grab`), diinterpolasi per frame 30 fps dan dikirim ke `crop` lewat `sendcmd` (1 perintah per frame). `irl`: median 1 dtk lalu batas kecepatan `max_pan_pct_per_s`; tanpa wajah → tahan posisi terakhir (awal: tengah). `podcast`: potongan langsung ke wajah pembicara aktif, tidak lebih sering dari `switch_hold_ms`; tanpa giliran bicara → tahan. Pemetaan pembicara → wajah memakai urutan (pembicara pertama ↔ wajah paling kiri) kecuali `speaker_faces` diberikan — belum ada pencocokan gerak bibir; keterbatasan ini perlu dicek di evaluasi T-062. Muat giliran bicara dari `transcript_segments` dikerjakan di T-046 | `layout/crop_path.py` | Menunggu |
| 29 | Bentuk respons yang tidak dirinci di 06-api.md: `GET /layout-presets` → `{items:[{id,code,name,is_builtin,params}]}`; `GET /channels` → `{items:[{id,platform,external_id,name,default_layout_preset,default_regions,stream_count}],total}`; `POST /channels` hanya membuat Kanal `local` (nama 1–200, nama sama tanpa beda huruf → 409 + `existing_channel_id`); `PATCH /streams/{id}/channel` `{channel_id}` → `{stream}` (Kanal platform apa pun boleh); `GET /streams/{id}/regions` → `{stream_id, detected, suggested_layout_preset, regions, channel, message}` dengan `message` = teks FR-006 bila deteksi selesai, saran `center_crop`, tanpa region. `PUT /clips/{id}/regions`: replace per role; role harus milik preset (`gaming`/`custom`: cam, content; `split_two`/`podcast`: face_a, face_b; `irl`/`center_crop`: tidak ada) dan override gabungan harus lengkap (custom: 1–2 region); Klip `rendering` → 409; `rendered`/`render_failed` → `approved`; `apply_to_stream_clips` hanya Klip `candidate`/`approved` lain. Urutan tumpukan `custom` = urutan role (cam di atas) karena tabel tidak punya kolom urutan. `GET /media/streams/{id}/frame`: `w` 16–1280 (default 640), `t_ms` > durasi → 400, video belum ada → 409 `INVALID_STATE`, cache lewat `Cache-Control: private, max-age=60` | `layouts.py`, `api/routes/layouts.py`, `api/routes/media.py` | Menunggu, usul tambah ke 06-api.md |
| 30 | Sinyal Audio: loudness = RMS dBFS per detik dari PCM mono 8 kHz (FFmpeg pipe, lantai −100 dB untuk hening digital; dipilih alih-alih `ebur128`/`astats` karena lebih sederhana & bisa dibatalkan). Satuan = simpangan baku loudness seluruh stream (min. 1 dB). Pemetaan kenaikan terhadap rata-rata 60 dtk sebelumnya: ≤ 1σ → 0, 2σ → 0,8, ≥ 2,25σ → 1 (tanpa ambang 1σ, fluktuasi wajar audio tenang sudah ±0,4 sehingga melanggar "jendela tenang < 0,3"). Sinyal jendela = maksimum per detik. Video tanpa audio → array kosong (sinyal 0) | `highlight/audio_signal.py` | Menunggu; kalibrasi di T-062 |
| 31 | Sinyal Chat: ember 10 dtk setelah digeser mundur `chat_delay_ms` (offset < 0 diabaikan); bobot reaksi 1,5× dihitung ulang dari teks dengan `chat_reaction_words` saat skor (kolom `is_reaction` hanya hasil impor); rasio terhadap median ember ±150 dtk dengan lantai 1 pesan; sinyal = (rasio − 1)/4 dibatasi 0–1 (5× median = 1); sinyal jendela = ember tertinggi yang beririsan. BR-002 (`highlight/scoring.py`): tanpa chat → `w_chat` dibagi proporsional ke audio & LLM; LLM null → bobot audio+chat dinormalkan ulang dan `partial = true`; skor dibulatkan ke integer 0–100. Pembaca Pengaturan lewat Connection: `app_settings.value` | `highlight/chat_signal.py`, `highlight/scoring.py` | Menunggu; kalibrasi di T-062 |

## Sengaja ditunda ke task tertentu

| Hal | Ke task |
|---|---|
| `providers/*.json` (respons rekaman per penyedia) dibuat dari dokumentasi resmi bersama adapternya (Deepgram T-028 & AssemblyAI T-029 sudah) | T-038 |
| Status Klip saat Job `render` sukses/gagal (pipeline baru menangani stream) | T-046 |
| `cancel` pada `record_live` = `stop` (gabung segmen) ; event `live.position` | T-051 |
| Tab P-07 Akun Unggah, Caption, Gaya Subtitle (sengaja belum ditampilkan) | v1.1, T-050, T-045 |
| Analisis live per blok (scope transcribe/score) | v1.1 (FR-013) |
| `POST /streams` mode `live` sementara ditolak 400 "Rekam live belum tersedia di versi ini."; tombol Rekam Live & checkbox "Analisis selama live" di P-01 | T-051, T-053 |
| Transkripsi rentang (Penanda Live) belum mencegah kata ganda dengan transkripsi seluruh stream sesudahnya ("hanya rentang yang belum ditranskripsi") | T-051, T-052 |
| `score_highlights` harus membatasi jendela ke rentang yang ditranskripsi (`checkpoint.range` Job transcribe terakhir) | T-037, T-039 |
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

- Keputusan #2–#9 di atas: setujui atau ubah.
- Ruang disk C: sekitar 33 GB (disarankan ≥ 50 GB); kosongkan atau arahkan `KLIPIN_HOME` ke drive
  lain sebelum mengunduh VOD sungguhan di Fase 2.
- Pertanyaan terbuka bawaan spesifikasi tetap berlaku (lihat `docs/spec/00-README.md`).
