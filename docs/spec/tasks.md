# Tasks Implementasi: Klipin
> Versi 1.0 · 2026-11-20 · Sumber: 01-prd.md (v1.2) s/d 10-roadmap.md (v1.0)
> Cara pakai: kerjakan berurutan, centang `[x]` saat selesai. Jangan mulai fase baru sebelum checkpoint fase sebelumnya lulus. `[P]` = boleh dikerjakan paralel dengan task lain di fase yang sama.
> Fase di sini memetakan 10-roadmap.md: Fase 0–1 = M0 Fondasi, Fase 2 = MVP-1, Fase 3 = MVP-2, Fase 4 = pengujian & rilis pribadi. v1.1 (unggah otomatis) ada di bagian "Di luar MVP".

## Fase 0: Setup
- [x] **T-001** Inisialisasi monorepo sesuai 04-arsitektur.md §6: `pyproject.toml` (uv, Python 3.11+, entry point `klipin`), `backend/klipin/`, `frontend/` (React 18 + Vite + TypeScript + Tailwind + TanStack Query), `tests/`, `docs/spec/`. _(setup)_
  - Selesai jika: `uv sync` dan `cd frontend && pnpm install && pnpm build` berhasil tanpa error.
- [x] **T-002** CLI `klipin` dengan subperintah `start | api | worker | doctor | update-ytdlp` (kerangka; `start` menjalankan API + Worker sebagai dua proses). _(setup)_
  - Selesai jika: `uv run klipin --help` menampilkan semua subperintah; `uv run klipin start` menyalakan dua proses dan Ctrl+C mematikan keduanya.
- [x] **T-003** `config.py` membaca env (04-arsitektur.md §8.2) + `.env.example` berisi **semua** variabel di tabel itu (termasuk `KLIPIN_PROVIDERS`, `KLIPIN_OAUTH_REDIRECT_BASE`, kredensial Google/TikTok/Meta kosong). `.env` masuk `.gitignore`. _(setup)_
  - Selesai jika: semua env var terdaftar di `.env.example` dengan keterangan; nilai default sesuai tabel.
- [x] **T-004** [P] Logging terstruktur `structlog` JSON ke `{KLIPIN_HOME}/logs/klipin.log` (rotasi 10 MB × 5) + filter yang menyamarkan pola API key/token. _(setup, NFR-005)_
  - Selesai jika: log tercipta; unit test memastikan string mirip key tersamarkan.
- [x] **T-005** [P] `klipin doctor`: cek Python, FFmpeg/FFprobe (libx264 & libass), yt-dlp, SQLite ≥ 3.35 + JSON1, keyring, ruang disk, port bebas. _(FR-021)_
  - Selesai jika: output tabel hijau/merah per item; FFmpeg tanpa libass terdeteksi merah.
- [x] **T-006** [P] CI GitHub Actions (ubuntu + windows): lint (ruff, eslint), `pytest` dengan `KLIPIN_PROVIDERS=fake`, build frontend. _(setup)_
  - Selesai jika: pipeline hijau pada commit kosong-fitur.
- [x] **T-007** [P] Siapkan fixture uji 09-testing.md §5 (video 30 detik gaming/podcast/IRL/tanpa wajah/tanpa audio/rusak, audio 25 menit, chat jsonl, folder `fixtures/providers/`). _(setup)_
  - Selesai jika: fixture ada di `tests/fixtures/` dengan README sumber/lisensi dan ground truth Region Cam (JSON).

**Checkpoint 0:** `uv run klipin start` menyalakan API kosong di `http://127.0.0.1:8765` yang menyajikan halaman React kosong; `klipin doctor` jalan; CI hijau.

## Fase 1: Fondasi (database, Job, keamanan lokal, pengaturan)
- [x] **T-008** SQLAlchemy + Alembic, sesi SQLite (WAL, `foreign_keys=ON`, `busy_timeout=5000`); migrasi awal berisi **seluruh** DDL 05-database.md §5 (termasuk `jobs.purpose`). _(setup)_
  - Selesai jika: `alembic upgrade head` dari nol berhasil; tes constraint: CHECK durasi Klip, BR-009 unik per platform, `purpose`, Region Cam satu pemilik, menolak data tidak valid.
- [x] **T-009** Seed 05-database.md §6.2 (Preset Layout, Gaya Subtitle, `settings`) sebagai migrasi data idempoten. _(FR-007, FR-017, FR-021)_
  - Selesai jika: 6 preset, 3 gaya bawaan, semua kunci settings ada setelah migrasi; menjalankan ulang tidak menggandakan.
- [x] **T-010** Backup harian `klipin.db` (SQLite online backup, simpan 7) + backup sebelum migrasi. _(NFR-010)_
  - Selesai jika: tes memajukan jam → file backup tercipta & dirotasi.
- [x] **T-011** Aplikasi FastAPI: bind loopback `127.0.0.1` + `::1`, token sesi acak disisipkan ke `index.html`, middleware wajib `X-Klipin-Token` (atau `?t=` untuk media/SSE), cek header `Host`, tanpa CORS, format error standar 06-api.md §1. _(ADR-009, BR-012, NFR-005)_
  - Selesai jika: TC-070, TC-071, TC-072 lulus.
- [x] **T-012** Wrapper keyring (`secrets.py`) + fallback `.env` dengan flag peringatan; endpoint `PUT/DELETE /secrets/{name}`, `POST /secrets/{name}/test` (penyedia palsu dulu). _(FR-021, ADR-007)_
  - Selesai jika: TC-042 lulus; nilai rahasia tidak pernah muncul di respons/log.
- [x] **T-013** `GET/PATCH /settings` dengan validasi 02-requirements.md §3 (bobot total 1,00, Jeda Chat, dst.). _(FR-021)_
  - Selesai jika: TC-041 lulus; respons memuat semua kunci seperti contoh 06-api.md.
- [x] **T-014** Worker loop: klaim atomik (04-arsitektur.md §3.1), `max_heavy_jobs` + 1 slot ringan, heartbeat 10 detik, penandaan Job terputus saat start, pembatalan subprocess ≤ 10 detik, registri handler per Jenis Job, `checkpoint` & `log_tail`. _(FR-023, ADR-002)_
  - Selesai jika: Job dummy berjalan, bisa dibatalkan, dan TC-046 (kill Worker lalu start ulang) lulus dengan Job dummy.
- [x] **T-015** Orkestrator pipeline (`pipeline.py`): aturan "Job sukses → Job berikutnya" sesuai tabel 04-arsitektur.md §3.1, dalam transaksi yang sama dengan penandaan `succeeded`; pembaruan status Stream Sumber. _(FR-001, FR-005, FR-012)_
  - Selesai jika: unit test rantai `download → detect_layout + transcribe → score_highlights → ready` dengan handler palsu.
- [x] **T-016** API Job: `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `/retry` (Job baru + `retry_of_job_id` + salin checkpoint), `/confirm`. _(FR-022, FR-023)_
  - Selesai jika: TC-045 lulus (dengan Job dummy); retry membuat Job baru dengan checkpoint tersalin.
- [x] **T-017** SSE `GET /events` (polling DB 1 detik, heartbeat 15 detik, maks. 5 koneksi) dengan event 06-api.md. _(FR-023)_
  - Selesai jika: TC-047 lulus.
- [x] **T-018** [P] Kerangka frontend: router hash, klien API (header token), hook SSE dengan reconnect, header global (indikator Job aktif), design token 08-ui-ux.md §5, komponen toast/modal/konfirmasi, daftar pintasan `?`. _(setup)_
  - Selesai jika: navigasi antar halaman kosong P-01…P-07 berjalan; indikator Job berubah saat Job dummy berjalan.
- [x] **T-019** [P] P-06 Antrean Job (tabel, log, Batalkan/Coba lagi, dialog konfirmasi pemakaian). _(FR-022, FR-023)_
  - Selesai jika: Job dummy terlihat progresnya real-time dan bisa dibatalkan dari UI.
- [x] **T-020** [P] P-07 Pengaturan tab Umum, API & Penyedia, Skor Highlight, Sistem (hasil `system/health` + `update-ytdlp`). Endpoint `GET /system/health`, `POST /system/update-ytdlp`. _(FR-021)_
  - Selesai jika: API key bisa diisi & dites (penyedia palsu), bobot tersimpan, hasil doctor tampil.

**Checkpoint 1:** Klipin jalan dengan DB tersedia (seed), Job dummy berjalan/dibatalkan/dicoba ulang dari UI dengan progres real-time, API terlindungi token (TC-070–TC-072 lulus), pengaturan & rahasia tersimpan.

## Fase 2: MVP-1 — klip dari VOD sampai Paket Unggah manual

### US-001 Impor VOD dari URL
- [x] **T-021** Modul `media/ytdlp.py`: `inspect(url)` (metadata, live status, chat replay, perkiraan ukuran) dan unduh VOD ≤ 1080p ke MP4 dengan progres & lanjutan. _(FR-001, INT-01)_
  - Selesai jika: unit test dengan respons yt-dlp tersimpan; unduhan fixture lokal berhasil dan bisa dilanjutkan.
- [x] **T-022** Endpoint `POST /streams/inspect`, `POST /streams` (mode `vod`), `GET /streams`, `GET /streams/{id}`; cek disk; deteksi duplikat; buat/temukan Kanal. _(FR-001)_
  - Selesai jika: TC-001–TC-004 lulus.
- [x] **T-023** Handler Job `download` + unduh chat replay YouTube (INT-02) ke `chat_messages` (tandai `is_reaction`, `has_chat`). _(FR-001, FR-010)_
  - Selesai jika: fixture chat jsonl terimpor dengan `offset_ms` benar; chat gagal tidak menggagalkan Job.
- [x] **T-024** [P] P-01 Beranda: kolom URL + inspect otomatis, kartu metadata, tombol Impor VOD, daftar 5 stream terakhir, banner izin konten. _(FR-001)_
  - Selesai jika: dari URL fixture sampai Stream Sumber terbentuk dan berpindah ke P-04 dengan progres pipeline.
- [x] **T-025** [P] P-02 Daftar Stream (tabel, filter status, ukuran file). _(FR-024)_
  - Selesai jika: stream tampil dengan status real-time.

### US-005 Transkripsi otomatis
- [x] **T-026** Antarmuka `Transcriber` + `FakeTranscriber` (deterministik dari fixture). _(FR-005, ADR-003)_
  - Selesai jika: pipeline bisa memakai penyedia palsu via `KLIPIN_PROVIDERS=fake`.
- [x] **T-027** Handler `transcribe`: ekstrak audio 16 kHz, potong 10 menit + overlap 2 detik ke `transcription_chunks`, deteksi bahasa chunk pertama, kirim per chunk dengan retry 2/4/8 detik, jahit overlap, normalisasi pembicara `S1/S2`, simpan segmen & kata, checkpoint per chunk, dukung `scope_start_ms/scope_end_ms`. _(FR-005)_
  - Selesai jika: TC-011–TC-014 lulus dengan `FakeTranscriber`.
- [x] **T-028** Adapter Deepgram (INT-04) + tes kontrak (sukses, 401, 429, 5xx). _(FR-005)_
  - Selesai jika: tes kontrak respx lulus; "Tes koneksi" berhasil dengan key asli (manual).
- [x] **T-029** [P] Adapter AssemblyAI (alur asinkron: unggah → transkrip → polling) + tes kontrak. _(FR-005)_
  - Selesai jika: tes kontrak lulus; bisa dipilih di Pengaturan.
- [x] **T-030** Konfirmasi perkiraan pemakaian: tahan `transcribe` (`awaiting_confirmation`) untuk stream > N menit, `usage_estimate` di `GET /jobs/{id}`, `confirm` dengan opsi rentang, batas durasi per Job. _(FR-022)_
  - Selesai jika: TC-043, TC-044 lulus; banner di P-04 & dialog di P-06 berfungsi.

### US-006 / US-007 Deteksi cam & Preset Layout
- [ ] **T-031** Handler `detect_layout`: sampling 1 frame/10 detik (maks. 600), MediaPipe (fallback OpenCV DNN), pengelompokan posisi wajah, aturan saran preset FR-006, simpan Region Cam (`source_stream_id`) & `suggested_layout_preset_id`, verifikasi default Kanal. _(FR-006)_
  - Selesai jika: TC-015, TC-016, TC-017 lulus.
- [ ] **T-032** Modul `media/ffmpeg.py` filtergraph per preset: `gaming`, `split_two`, `center_crop`, `custom` (statis) → kanvas 1080×1920 tanpa bar hitam. _(FR-007)_
  - Selesai jika: TC-018 lulus; snapshot frame untuk tiap preset statis sesuai.
- [ ] **T-033** Jalur crop dinamis `irl` (ikuti wajah, maks. pan 5%/detik) dan `podcast` (pembicara aktif dari diarization + wajah, tahan ≥ 1,5 detik) dengan sampling 5 fps di rentang Klip. _(FR-007, ADR-004)_
  - Selesai jika: TC-019 lulus; IRL tidak bergoyang (simpangan antar-detik ≤ 5% lebar).
- [ ] **T-034** Endpoint `GET /streams/{id}/regions`, `PUT /clips/{id}/regions` (override, simpan default Kanal, terapkan ke klip lain), `GET /channels`, `POST /channels`, `PATCH /streams/{id}/channel`, `GET /layout-presets`, `GET /media/streams/{id}/frame`. _(FR-006, FR-008)_
  - Selesai jika: TC-017 lulus lewat API; stream tanpa Kanal → 409 "Pilih Kanal dulu".

### US-008 Deteksi Kandidat Klip
- [ ] **T-035** Sinyal Audio (loudness per detik → z-score → lonjakan 0–1). _(FR-009)_
  - Selesai jika: TC-020 lulus.
- [ ] **T-036** [P] Sinyal Chat (per 10 detik, bobot kata reaksi 1,5×, normalisasi median 5 menit, geser Jeda Chat) + pembagian bobot saat chat tidak ada. _(FR-010, BR-002)_
  - Selesai jika: TC-021, TC-022 lulus.
- [ ] **T-037** `highlight_windows` (60 detik geser 30) + pra-seleksi BR-003. _(FR-011, BR-003)_
  - Selesai jika: unit test persentil & batas 120 jendela/jam.
- [ ] **T-038** Antarmuka `HighlightJudge` + `FakeJudge` + adapter Anthropic (structured output, validasi Pydantic, retry, paralel 4, `max_tokens` 300, model dari `settings.llm_models`). _(FR-011, INT-05)_
  - Selesai jika: TC-023, TC-024 lulus; tes kontrak adapter lulus.
- [ ] **T-039** Handler `score_highlights`: gabung skor BR-001/BR-002, koreksi rentang BR-004, non-overlap BR-005, jumlah BR-006, buat Klip `auto`/`candidate` (preset dari default Kanal → saran → `center_crop`), `POST /streams/{id}/rescore` memakai cache. _(FR-012)_
  - Selesai jika: TC-025, TC-026 lulus.

### US-009 Review & edit Klip
- [ ] **T-040** Endpoint Klip: `GET /streams/{id}/clips`, `GET /clips/{id}`, `PATCH /clips/{id}`, `approve/reject/restore/unapprove`, `POST /streams/{id}/clips` (manual), `POST /clips/{id}/snap`, `GET /streams/{id}/transcript`, `GET /streams/{id}/timeline`, `GET /streams/{id}/waveform`, `GET /media/streams/{id}/source` (Range). _(FR-014, FR-015)_
  - Selesai jika: TC-027–TC-032 lulus.
- [ ] **T-041** P-04 Review Klip: tiga kolom, kartu Klip (skor, kategori, alasan, badge), filter/urut, rincian Sinyal, timeline heatmap (klik lompat, seret buat Klip), pratinjau 9:16 tiruan CSS sesuai preset & Region Cam, pintasan `J/K/A/X/E/Spasi/←/→`, banner pipeline & konfirmasi pemakaian. _(FR-012, FR-014)_
  - Selesai jika: review 10 Klip hanya dengan keyboard (NFR-009); state kosong/memuat/error sesuai 08-ui-ux.md.
- [ ] **T-042** P-05 Editor Klip tab Layout & Info: trimmer (filmstrip + waveform, jepret batas kalimat, `[`/`]`), kartu Preset Layout, editor Region Cam drag/resize di atas frame sumber, opsi simpan default Kanal, simpan otomatis. _(FR-007, FR-008, FR-015)_
  - Selesai jika: koreksi Region Cam tersimpan & tampil di pratinjau ≤ 3 detik; validasi Region Cam berfungsi.

### US-010 / US-011 Subtitle
- [ ] **T-043** Modul `subtitles/`: bangun baris dari Kata Transkrip + `subtitle_overrides` (BR-011), aturan per baris (`max_words_per_line`, `max_chars_per_line`), generator ASS (`word_highlight` per kata, `sentence`) & SRT; endpoint `GET /clips/{id}/subtitles`. _(FR-016, FR-017)_
  - Selesai jika: unit test ASS/SRT; TC-031 (bagian subtitle) & TC-036 lulus.
- [ ] **T-044** Terjemahan EN→ID: `Translator` (Anthropic), `POST /clips/{id}/translate`, cache `translated_lines`, paksa mode `sentence` (BR-008). _(FR-016)_
  - Selesai jika: TC-033, TC-034, TC-035 lulus.
- [ ] **T-045** Gaya Subtitle: `GET/POST/PATCH/DELETE /subtitle-styles`, P-07 tab Gaya Subtitle, P-05 tab Subtitle (pemilih gaya & Bahasa Tampil, edit kata/sembunyikan/pemisah baris, sorot confidence rendah, kembalikan ke asli). Font bawaan dibundel di `fonts/`. _(FR-015, FR-016, FR-017)_
  - Selesai jika: edit kata di P-05 tercermin di pratinjau & `GET /clips/{id}/subtitles`; gaya bawaan tidak bisa dihapus.

### US-012 Render
- [ ] **T-046** Handler `render` `purpose=final`: potong rentang, filtergraph preset/jalur crop, burn ASS, H.264/AAC 1080×1920 30 fps preset `veryfast`, `.srt`, penamaan file, progres FFmpeg, status Klip (`rendering → rendered/render_failed`, batal → `approved`). Endpoint `POST /clips/{id}/render` (idempoten), `POST /streams/{id}/clips/render-approved`, `GET /media/clips/{id}/video|srt`. _(FR-018, BR-007)_
  - Selesai jika: TC-037–TC-040 lulus; NFR-002 diukur.
- [ ] **T-047** Render pratinjau `purpose=preview` (5 detik, Job ringan, tidak mengubah status, menimpa pratinjau lama) + `POST /clips/{id}/preview-render`, `GET /media/clips/{id}/preview`; tombol di P-05. _(FR-017)_
  - Selesai jika: TC-065 lulus.
- [ ] **T-048** [P] `POST /system/open-folder` (Explorer/Finder) + tombol "Buka folder" & "Unduh MP4/.srt" di P-04. _(FR-018, FR-025)_
  - Selesai jika: TC-066 lulus.

### US-017 / US-018 Paket Unggah manual
- [ ] **T-049** `GET /clips/{id}/upload-dialog` (kesiapan per platform; di MVP `auto_blockers` selalu berisi `PLATFORM_NOT_CONFIGURED` atau `ACCOUNT_NOT_CONNECTED`), `POST /clips/{id}/uploads` (mode `manual`, all-or-nothing, salin draf/teks, template caption), `GET /clips/{id}/uploads`, `POST /uploads/{id}/mark-posted` (validasi domain), `DELETE /uploads/{id}`. _(FR-025, FR-026, BR-007, BR-009, BR-013, BR-014)_
  - Selesai jika: TC-049–TC-055 lulus.
- [ ] **T-050** P-08 Dialog Unggah mode manual: centang platform, editor judul/caption/hashtag + penghitung batas, kartu Paket Unggah (unduh, salin caption, buka halaman upload dari `settings.manual_upload_urls`, buka folder, URL + Tandai sudah diposting, batalkan), badge unggah per platform di kartu P-04, P-07 tab Caption (template & URL halaman upload). Toggle Otomatis tampil tetapi nonaktif dengan alasan. _(FR-025, FR-026)_
  - Selesai jika: alur UF-04 cabang manual berjalan end-to-end; teks UI sesuai 08-ui-ux.md §7.

**Checkpoint 2 (MVP-1):** dari URL VOD YouTube nyata → Kandidat Klip → edit → render MP4 9:16 bersubtitle → Paket Unggah tersalin dan ditandai diposting, semua dari UI. TC-001–TC-004, TC-011–TC-043, TC-048 (sebagian: hapus belum), TC-049–TC-055, TC-065, TC-066 lulus. Jalankan A/B transkripsi (T-061) dan evaluasi kualitas putaran 1 (T-062) sebelum lanjut.

## Fase 3: MVP-2 — live, file lokal, penyimpanan, draf caption

### US-003 / US-004 Rekam live & Penanda Live
- [ ] **T-051** Handler `record_live`: ambil manifest HLS via yt-dlp, rekam FFmpeg per segmen 10 detik, segarkan manifest, sambung ulang < 60 detik (catat celah), berhenti saat stream selesai/`stop`, gabung segmen → `source.mp4`, hapus segmen (NFR-011), lanjut pipeline. Endpoint `POST /streams` mode `live`, `POST /streams/{id}/stop`, `GET /media/streams/{id}/live.m3u8` & segmen, event `live.position`. _(FR-003)_
  - Selesai jika: TC-007, TC-008 lulus dengan server HLS lokal; NFR-011 terpenuhi.
- [ ] **T-052** Penanda Live: `POST /streams/{id}/markers`, `PATCH /markers/{id}`, `GET /streams/{id}/markers`; buat Klip `live_marker` + Job `transcribe` rentang (`is_heavy=0`). _(FR-004)_
  - Selesai jika: TC-009, TC-010 lulus.
- [ ] **T-053** P-03 Monitor Live: player hls.js near-live, label durasi & delay, tombol "Klip N detik terakhir" (`M`), Tandai Mulai/Selesai dengan penghitung, Berhenti Rekam, indikator celah, panel Penanda & Kandidat Klip live; tombol Rekam Live di P-01. _(FR-003, FR-004)_
  - Selesai jika: alur UF-02 berjalan dengan server HLS lokal; Kandidat Klip dari penanda muncul ≤ 2 menit.

### US-002 Impor file lokal
- [ ] **T-054** `GET /fs/list` (tanpa mengikuti symlink, hanya metadata), `POST /streams/local` (FFprobe, validasi, opsi salin ke folder kerja), P-09 Penjelajah File. _(FR-002)_
  - Selesai jika: TC-005, TC-006, TC-073 lulus.

### Manajemen penyimpanan
- [ ] **T-055** `DELETE /streams/{id}/source-video` (pratinjau dampak + confirm), `DELETE /streams/{id}`, pembersihan audio chunk/frame setelah `ready`, ukuran per stream di P-02 + dialog konfirmasi. _(FR-024)_
  - Selesai jika: TC-048 lulus.

### US-019 Draf caption per platform
- [ ] **T-056** `CaptionWriter` (Anthropic, JSON per platform, batas panjang dari konfigurasi platform), `POST/PATCH /clips/{id}/captions`, cache `clips.caption_drafts` (tidak menimpa `edited`), fallback template; isi otomatis di P-08 + tombol "Buat ulang draf". _(FR-027)_
  - Selesai jika: TC-062, TC-063 lulus.

**Checkpoint 3 (MVP-2):** rekam live YouTube/Kick nyata, "Klip 60 detik terakhir" jadi Kandidat Klip ≤ 2 menit, file lokal bisa diimpor, video sumber bisa dihapus dengan aman, draf caption otomatis muncul di dialog unggah. TC-005–TC-010, TC-048, TC-062, TC-063 lulus.

## Fase 4: Pengujian & rilis pribadi
- [ ] **T-057** Tes E2E Playwright UF-01, UF-03, UF-04 (manual) dengan `KLIPIN_PROVIDERS=fake`, masuk CI. _(semua FR Must)_
  - Selesai jika: E2E hijau di CI ubuntu & windows.
- [ ] **T-058** Uji keamanan lokal TC-070–TC-076 otomatis (kecuali TC-072 manual). _(NFR-005, NFR-006)_
  - Selesai jika: semua lulus; grep rahasia di log/DB/respons bersih.
- [ ] **T-059** Uji non-fungsional di laptop acuan: NFR-001, NFR-002, NFR-003, NFR-008, NFR-009, NFR-010 (09-testing.md §4.1). _(NFR)_
  - Selesai jika: hasil dicatat di `docs/spec/09-testing.md` (Riwayat Perubahan) dan target terpenuhi atau dicatat sebagai item roadmap.
- [ ] **T-060** Smoke test manual Windows 11 + macOS (`klipin doctor`, UF-01, UF-02, UF-03, UF-04 manual) dan README instalasi pengguna (prasyarat, langkah 04-arsitektur.md §8.3, runbook §8.5). _(NFR-007)_
  - Selesai jika: kedua OS lulus; README cukup untuk instalasi dari nol.
- [ ] **T-061** A/B penyedia transkripsi (Deepgram vs AssemblyAI) pada Set Evaluasi; tetapkan default `transcriber_provider`; catat hasil di 07-integrasi.md. _(FR-005)_
  - Selesai jika: keputusan & angka tercatat.
- [ ] **T-062** Evaluasi kualitas 09-testing.md §4.2 (relevansi kandidat, layout, akurasi subtitle, waktu kerja, penanda live); kalibrasi bobot/ambang default bila perlu. _(FR-006, FR-012, FR-016)_
  - Selesai jika: metrik tercatat; akurasi subtitle ≥ 80% (syarat rilis).

**Checkpoint 4:** kriteria siap rilis 09-testing.md §6 terpenuhi (tanpa butir mode otomatis).

## Di luar MVP (dicatat, belum dikerjakan — fase v1.1 di 10-roadmap.md)
- **F-07 Analisis live bertahap** (FR-013, TC-064): Job `transcribe` + `score_highlights` per blok 5 menit selama `record_live`.
- **Kerangka unggah otomatis** (FR-019, FR-020): antarmuka `Publisher`, OAuth bersama (`/oauth/{platform}/start`, `/oauth/callback/{platform}`, `/oauth/{platform}/targets`), `GET /upload-accounts`, P-07 tab Akun Unggah, handler Job `upload`, `retry`/`switch-manual`, toggle Otomatis aktif di P-08 (TC-056–TC-061).
- **F-12 TikTok** (INT-10) → **F-12 Instagram** (INT-11) → **F-12 Facebook** (INT-12) → **F-11 YouTube** (INT-07): satu adapter per platform + tes kontrak + smoke test unggahan private.
- **INT-03 Chat live Kick (eksperimental)**, mati secara default.
- v2: transkripsi lokal, penjadwalan posting, banyak akun per platform, klip 16:9, mode review layar penuh, notifikasi desktop.

## Ringkasan
| Fase | Jumlah task | FR yang tercakup |
|---|---|---|
| 0 Setup | 7 (T-001–T-007) | setup, FR-021 |
| 1 Fondasi | 13 (T-008–T-020) | FR-001, FR-005, FR-007, FR-012, FR-017, FR-021, FR-022, FR-023 |
| 2 MVP-1 | 30 (T-021–T-050) | FR-001, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-014, FR-015, FR-016, FR-017, FR-018, FR-022, FR-024, FR-025, FR-026 |
| 3 MVP-2 | 6 (T-051–T-056) | FR-002, FR-003, FR-004, FR-024, FR-027 |
| 4 Pengujian & rilis | 6 (T-057–T-062) | semua FR Must, NFR |
| **Total MVP** | **62** | 24 dari 27 FR; FR-013, FR-019, FR-020 di v1.1 |

Cakupan FR prioritas Must (F-01, F-04, F-05, F-06, F-08, F-09, F-10, F-13, F-15, F-16): FR-001, FR-005–FR-012, FR-014–FR-018, FR-021–FR-023, FR-025, FR-026, semuanya punya minimal satu task.
