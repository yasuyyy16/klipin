# Rencana Pengujian: Klipin
> Versi 1.1 · 2026-11-20 · Status: Draf · Dokumen terkait: 02-requirements.md, 03-user-flow.md, 04-arsitektur.md, 05-database.md, 06-api.md, 07-integrasi.md, 08-ui-ux.md

## 1. Strategi
| Level | Yang diuji | Alat | Alasan |
|---|---|---|---|
| Unit | Aturan bisnis murni: rumus skor & pembagian bobot (BR-001, BR-002), pra-seleksi (BR-003), koreksi durasi (BR-004), non-overlap (BR-005), jumlah kandidat (BR-006), penjahitan chunk transkrip, normalisasi pembicara, pembangun baris subtitle & ASS/SRT, matematika Region Cam & filtergraph per preset, pemetaan visibilitas per platform, validasi URL postingan | pytest, hypothesis (property-based untuk rentang waktu) | Logika paling rawan salah dan paling murah diuji tanpa I/O |
| Integrasi API + DB | Endpoint FastAPI + SQLite file sementara: transisi status (409), validasi (400), constraint DB (BR-009, CHECK durasi), pembuatan Job & orkestrasi pipeline, SSE | pytest + httpx `AsyncClient`, DB SQLite baru per test | Memastikan kontrak 06-api.md dan constraint 05-database.md benar-benar dijaga |
| Integrasi Worker | Handler Job dengan biner asli (FFmpeg, yt-dlp offline/fixture) dan penyedia palsu: `transcribe` (checkpoint & retry), `detect_layout`, `score_highlights`, `render` | pytest, video fixture pendek, `FakeTranscriber`, `FakeJudge`, `FakePublisher` | Pipeline adalah inti produk; penyedia palsu membuat tes deterministik & gratis |
| Kontrak adapter | Adapter Deepgram/AssemblyAI/LLM/YouTube/TikTok/Instagram/Facebook terhadap respons rekaman (sukses, 401, 429, 5xx, error audit/private, status asinkron) | pytest + respx (mock HTTP) dengan fixture JSON | Mendeteksi kesalahan parsing & retry tanpa memanggil API berbayar/membuat postingan sungguhan |
| E2E | Alur UF-01, UF-03, UF-04 (manual) di browser dengan backend + Worker asli dan penyedia palsu | Playwright | Memastikan UI, SSE, dan pintasan keyboard bekerja bersama |
| Kualitas (manual terukur) | Relevansi Kandidat Klip, akurasi subtitle, ketepatan Region Cam, A/B penyedia transkripsi | Lembar penilaian (bagian 4.2) | Metrik keberhasilan PRD bersifat kualitatif dan butuh penilaian manusia |
| Asap (smoke) API nyata | Satu panggilan nyata per penyedia yang dikonfigurasi ("Tes koneksi") + satu unggahan `private` ke akun uji per platform | Manual, sebelum rilis | Memastikan kredensial & versi API saat ini masih cocok |

Prinsip: tes tidak boleh memanggil API berbayar atau memposting ke akun sungguhan secara otomatis. Semua penyedia eksternal punya implementasi palsu yang dipilih lewat env `KLIPIN_PROVIDERS=fake`.

## 2. Kasus Uji Fungsional
Minimal satu kasus sukses + satu kasus gagal per FR prioritas Must; FR Should/Could diuji di fasenya (10-roadmap.md).

| ID | FR | Skenario | Langkah | Hasil yang diharapkan |
|---|---|---|---|---|
| TC-001 | FR-001 | Impor VOD YouTube valid | `POST /streams/inspect` lalu `POST /streams` (mode vod) dengan yt-dlp diarahkan ke fixture | 201; Stream Sumber `queued`; Job `download` dibuat; setelah selesai → `processing`, Job `detect_layout` + `transcribe` ada |
| TC-002 | FR-001 | URL tidak didukung | `POST /streams/inspect` dengan `https://vimeo.com/123` | 400 `URL_NOT_SUPPORTED`, pesan sesuai 08-ui-ux.md, tidak ada baris baru |
| TC-003 | FR-001 | Disk tidak cukup | Simulasi `disk_free_bytes` < ukuran × 1,5 | 409 `INSUFFICIENT_DISK` dengan `required_bytes` & `free_bytes` |
| TC-004 | FR-001 | Impor ganda video yang sama | `POST /streams` dua kali dengan URL sama | Kedua 409 `INVALID_STATE` + `existing_stream_id` |
| TC-005 | FR-002 | File lokal valid | `POST /streams/local` dengan fixture mp4 30 detik | 201; durasi = 30.000 ms ± 50; Job `transcribe` + `detect_layout` |
| TC-006 | FR-002 | File tanpa audio | `POST /streams/local` dengan mp4 tanpa trek audio | 400, pesan "Video tidak memiliki audio…" |
| TC-007 | FR-003 | Rekam live (simulasi) | Sumber HLS lokal (FFmpeg memutar fixture sebagai HLS live) → `POST /streams` mode live | Segmen pertama ≤ 30 detik; `live.position` SSE terkirim; `stop` → segmen digabung, `processing` |
| TC-008 | FR-003 | Putus < 60 detik | Hentikan server HLS 20 detik lalu nyalakan | Rekaman berlanjut, celah tercatat di `checkpoint.gaps_ms` |
| TC-009 | FR-004 | Klip 60 detik terakhir | Saat rekaman 2 menit, `POST /markers {last_n_seconds, 60}` | Penanda [60.000, 120.000] ms; Klip `candidate` `origin=live_marker`; Job `transcribe` `is_heavy=0`; `clip.created` ≤ 2 menit |
| TC-010 | FR-004 | Rekaman baru 20 detik | `POST /markers` 60 detik saat rekaman 20 detik | Rentang [0, 20.000]; `info` = "Rekaman baru 20 detik" |
| TC-011 | FR-005 | Transkripsi berhasil multi-chunk | Audio 25 menit (3 chunk) dengan `FakeTranscriber` | Kata urut naik, tanpa duplikat di zona tumpang tindih, tanpa celah > 2 detik; `detected_language` terisi |
| TC-012 | FR-005 | 429 di satu chunk | Fake mengembalikan 429 dua kali di chunk 2 | Chunk 2 dicoba ulang (≤ 3×) lalu sukses; chunk 1 tidak dikirim ulang |
| TC-013 | FR-005, FR-023 | Gagal di tengah lalu coba ulang | Fake gagal permanen di chunk 2 → Job `failed` → `POST /jobs/{id}/retry` | Job baru hanya mengirim chunk 2–3 (`transcription_chunks` `done` dilewati) |
| TC-014 | FR-005 | API key kosong | Hapus secret, jalankan `transcribe` | Job `failed` dengan pesan API key; tidak ada request ke penyedia |
| TC-015 | FR-006 | Deteksi facecam gaming | Fixture gameplay + facecam tetap kanan bawah | Preset tersaran `gaming`; IoU Region Cam `cam` vs ground truth ≥ 0,8 |
| TC-016 | FR-006 | Tanpa wajah | Fixture layar game saja | Preset `center_crop` + pesan wajah tidak terdeteksi |
| TC-017 | FR-006, FR-008 | Default Kanal dipakai | Simpan Region Cam default Kanal → impor stream baru Kanal sama | Klip memakai `regions.source = channel` tanpa koreksi |
| TC-018 | FR-007 | Frame output gaming | Render Klip preset `gaming` | MP4 1080×1920; analisis frame: area 0–35% berisi crop cam, tanpa bar hitam (piksel tepi bukan hitam penuh) |
| TC-019 | FR-007 | Podcast tidak goyang | Diarization palsu bergantian tiap 0,5 detik | Jalur crop berpindah maks. 1× per 1,5 detik |
| TC-020 | FR-009 | Sinyal Audio lonjakan | Audio tenang + teriakan disisipkan di menit 10 | Jendela menit 10 ≥ 0,8; jendela tenang < 0,3 |
| TC-021 | FR-010 | Sinyal Chat dengan jeda | Chat palsu lonjakan 5× median di detik 600, Jeda Chat 8 detik | Puncak Sinyal Chat di jendela ±10 detik dari detik 592 |
| TC-022 | FR-010, BR-002 | Tanpa chat | Stream `has_chat=0` | Bobot chat dibagi proporsional ke audio & LLM; skor tetap terhitung |
| TC-023 | FR-011 | JSON LLM tidak valid | `FakeJudge` mengembalikan teks bebas 2× | Coba ulang 1×, lalu `llm_status=invalid`, Sinyal LLM null, Klip ditandai `score_partial` |
| TC-024 | FR-011, BR-003 | Batas pra-seleksi | Stream 1 jam dengan lonjakan di mana-mana | Panggilan `FakeJudge` ≤ 120 (NFR-012) |
| TC-025 | FR-012 | Kandidat valid | Stream 3 jam fixture sinyal sintetis | 1–20 Kandidat Klip, durasi 15–90 detik, overlap ≤ 5 detik, urut skor turun, semua skor ≥ 40 |
| TC-026 | FR-012 | Hitung ulang skor | Ubah bobot → `POST /streams/{id}/rescore` | Klip `auto`/`candidate` diganti; Klip `approved`/`rendered`/`live_marker` tidak berubah; `FakeJudge` tidak dipanggil untuk jendela `done` |
| TC-027 | FR-014 | Setujui & tolak | `approve` lalu `reject` lalu `restore` | Status `approved` → `rejected` → `candidate` |
| TC-028 | FR-014, BR-004 | Setujui durasi 100 detik | Klip `live_marker` 100 detik → `approve` | 400 `VALIDATION_ERROR` (`duration_ms`); CHECK DB juga menolak update langsung |
| TC-029 | FR-014 | Klip manual dari timeline | `POST /streams/{id}/clips` rentang 40 detik | Klip `manual`/`candidate` dengan subtitle dari kata yang ada |
| TC-030 | FR-015 | Jepret batas kalimat | `POST /clips/{id}/snap` di tengah kalimat | `snapped_ms` = akhir Segmen Transkrip terdekat (±2 detik) |
| TC-031 | FR-015, BR-011 | Edit kata subtitle | PATCH `subtitle_overrides` "gua"→"gue" → render | .srt & frame berisi "gue"; `transcript_words` tetap "gua" |
| TC-032 | FR-015 | Edit Klip yang sudah dirender | PATCH judul pada Klip `rendered` | Status `approved`, `needs_rerender=true` |
| TC-033 | FR-016 | Terjemahan EN→ID | Stream `en`, PATCH `subtitle_language=id` → `translate` | `translated_lines` timestamp = baris asli; mode efektif `sentence` + warning |
| TC-034 | FR-016 | Terjemahan gagal | Fake LLM error 2× | 502 `UPSTREAM_ERROR`; UI kembali ke `source` dengan pesan |
| TC-035 | FR-016 | Terjemahan di stream Indonesia | `subtitle_language=id` saat `detected_language=id` | 400/409 ditolak |
| TC-036 | FR-017 | Highlight per kata tepat waktu | Render gaya "Highlight Kata" | Tag ASS per kata sesuai `start_ms` (±100 ms); frame pada waktu kata menunjukkan warna highlight |
| TC-037 | FR-018 | Render sukses | `POST /clips/{id}/render` Klip `approved` 60 detik | MP4 1080×1920, H.264/AAC, durasi ±0,1 detik, .srt ada, status `rendered` |
| TC-038 | FR-018, BR-007 | Render Klip candidate | `render` pada `candidate` | 409 "Setujui klip dulu sebelum render." |
| TC-039 | FR-018 | FFmpeg gagal | Rusak file sumber sebelum render | `render_failed` + baris error FFmpeg; `retry` bisa dijalankan |
| TC-040 | FR-018 | Render idempoten | `render` dua kali cepat | Satu Job; panggilan kedua 200 mengembalikan Job yang sama |
| TC-041 | FR-021 | Total bobot salah | PATCH bobot 0,3/0,3/0,5 | 400 "Total bobot harus 100%." |
| TC-042 | FR-021 | API key termasking | PUT secret lalu GET settings | Hanya `masked` (4 karakter akhir); nilai utuh tidak pernah ada di respons/log |
| TC-043 | FR-022 | Konfirmasi pemakaian | Stream 2 jam 10 menit, konfirmasi aktif | Job `transcribe` `awaiting_confirmation=1`; tidak jalan sampai `confirm proceed=true` |
| TC-044 | FR-022 | Melebihi batas durasi | Batas 60 menit, stream 2 jam | Job tertahan; `confirm` dengan `range` 0–60 menit memproses rentang itu saja |
| TC-045 | FR-023 | Batalkan Job | `cancel` saat `render` berjalan | Subprocess berhenti ≤ 10 detik; `cancelled`; Klip kembali `approved` |
| TC-046 | FR-023, NFR-004 | Aplikasi ditutup paksa | Kill proses Worker saat `transcribe` lalu start ulang | Job lama `failed` "Terhenti karena aplikasi ditutup"; DB utuh; retry melanjutkan |
| TC-047 | FR-023 | SSE progres | Buka `GET /events`, jalankan Job | `job.updated` diterima ≤ 3 detik setelah perubahan |
| TC-048 | FR-024 | Hapus video sumber | `DELETE /streams/{id}/source-video` tanpa lalu dengan `confirm` | Pratinjau dampak (jumlah Klip belum dirender); setelah confirm file hilang, `video_path` null, render Klip lain → 409 `SOURCE_DELETED` |
| TC-049 | FR-025 | Paket Unggah manual | Klip `rendered`, `POST /clips/{id}/uploads` TikTok+Instagram manual | 2 Unggahan `manual`/`pending`; `package` berisi URL video/srt, `caption_full` (caption + hashtag + template), `upload_page_url` |
| TC-050 | FR-025, BR-007 | Unggah sebelum render | `upload-dialog` / `uploads` pada Klip `approved` | 409 "Render klip dulu." |
| TC-051 | FR-025, BR-009 | Unggahan ganda per platform | Buat Unggahan TikTok manual lalu TikTok auto | 409 `DUPLICATE_UPLOAD`; index unik DB juga menolak |
| TC-052 | FR-025, BR-013 | Otomatis tanpa akun | `uploads` mode `auto` YouTube tanpa Akun Unggah | 409 `AUTO_NOT_AVAILABLE`; tidak ada Unggahan dibuat (all-or-nothing) |
| TC-053 | FR-026 | Tandai sudah diposting | `mark-posted` dengan URL TikTok valid | `uploaded`, URL tersimpan, badge muncul di daftar Klip |
| TC-054 | FR-026 | URL platform salah | `mark-posted` URL YouTube pada Unggahan TikTok | 400 "URL tidak sesuai platform TikTok." |
| TC-055 | FR-026 | Batalkan manual | `DELETE /uploads/{id}` pada manual `pending` | Record hilang; platform bisa dipilih lagi |
| TC-056 | FR-019 | OAuth state salah | `GET /oauth/callback/tiktok?code=x&state=palsu` | 400; tidak ada Akun Unggah |
| TC-057 | FR-019 | Pilih Halaman Facebook | Callback Meta palsu dengan 2 Halaman → `POST /oauth/facebook/targets` | Akun Unggah `facebook` dengan `target_id` terpilih; `connected` |
| TC-058 | FR-020 | Unggah otomatis paralel | `FakePublisher` YouTube sukses, TikTok gagal | YouTube `uploaded`; TikTok `failed`; keduanya Job terpisah |
| TC-059 | FR-020 | Dipaksa private | Fixture respons TikTok `unaudited_client_can_only_post_to_private_accounts` | Unggahan `failed` dengan pesan terjemahan 07-integrasi.md; tombol "Unggah manual saja" (`switch-manual`) membuat Unggahan manual |
| TC-060 | FR-020 | Status publikasi asinkron | Fixture Instagram container `IN_PROGRESS` ×3 lalu `FINISHED` | Polling berhenti saat `FINISHED`, `media_publish` dipanggil sekali, `external_post_id` & URL terisi |
| TC-061 | FR-020 | Token kedaluwarsa | Fixture 401/`invalid_grant` | Akun `needs_reauth`; Unggahan `failed` dengan pesan hubungkan ulang |
| TC-062 | FR-027 | Draf caption | `POST /clips/{id}/captions` youtube+tiktok | Draf dalam batas panjang platform, 3–8 hashtag berawalan `#` |
| TC-063 | FR-027 | Edit tidak ditimpa | PATCH caption TikTok → POST captions tanpa `force` | Caption TikTok tetap hasil edit (`edited=true`) |
| TC-064 | FR-013 | Analisis selama live | Rekaman simulasi 12 menit, opsi aktif | Kandidat Klip blok 0–10 menit muncul sebelum `stop`; setelah stop, blok tersebut tidak ditranskripsi ulang |
| TC-065 | FR-017 | Render pratinjau 5 detik | `POST /clips/{id}/preview-render` pada Klip `approved` | Job `render` `purpose=preview`; file pratinjau 5 detik ±0,1; status Klip tetap `approved` |
| TC-066 | FR-018, FR-025 | Buka folder | `POST /system/open-folder {target:"clip"}` untuk Klip `rendered` dan untuk Klip belum dirender | 200 dan explorer terbuka (cek manual); 404 untuk yang belum dirender |

## 3. Uji Hak Akses & Keamanan Lokal
Klipin hanya punya satu peran (Pengguna), jadi uji antar-peran tidak berlaku. Pengujian difokuskan pada perlindungan API lokal (ADR-009) dan penanganan rahasia.

| ID | Pelaku | Mencoba | Hasil yang diharapkan |
|---|---|---|---|
| TC-070 | Halaman web lain di browser yang sama | `fetch('http://127.0.0.1:8765/api/v1/streams', {method:'POST'})` tanpa token | 403 `FORBIDDEN_ORIGIN`; tidak ada header CORS di respons |
| TC-071 | Serangan DNS rebinding | Request dengan `Host: evil.example:8765` | 403 |
| TC-072 | Perangkat lain di LAN | Akses `http://{ip-LAN}:8765` | Koneksi ditolak (server hanya bind `127.0.0.1`) |
| TC-073 | Path traversal | `GET /media/clips/../../klipin.db` dan `GET /fs/list?path=` ke folder sistem | Media hanya dari ID DB (404 untuk path aneh); `/fs/list` hanya menampilkan nama/ukuran, tanpa isi file |
| TC-074 | Callback OAuth palsu | `state` dipakai ulang atau milik platform lain | 400; token tidak ditukar |
| TC-075 | Kebocoran rahasia | Jalankan semua tes lalu grep `logs/`, respons API, dan `klipin.db` untuk API key/token uji | Tidak ditemukan |
| TC-076 | Injeksi SQL/XSS | Judul Klip/caption berisi `'); DROP TABLE clips;--` dan `<script>` | Tersimpan sebagai teks; UI merender ter-escape; judul YouTube dengan `<>` ditolak validasi |

## 4. Uji Non-Fungsional

### 4.1 Performa, ketahanan, kompatibilitas
| NFR | Uji | Target |
|---|---|---|
| NFR-001 | VOD 3 jam sudah terunduh, ukur tahap lokal (ekstrak audio, deteksi layout, Sinyal Audio/Chat) di laptop acuan (4 core, 16 GB, tanpa GPU) | ≤ 15 menit |
| NFR-002 | 10 render Klip 60 detik preset `gaming` & `podcast` | Median ≤ 2 menit |
| NFR-003 | P-04 dengan 200 Klip; ukur tampil daftar & pratinjau frame | ≤ 2 detik |
| NFR-004 | TC-046 | DB utuh, Job bisa dilanjutkan |
| NFR-005, NFR-006 | TC-070–TC-075; review layar persetujuan tiap platform (scope minimum) | Lulus semua |
| NFR-007 | Smoke test manual di Windows 11 + Chrome/Edge, macOS + Chrome/Firefox | Alur UF-01, UF-03, UF-04 (manual) lulus |
| NFR-008 | API key transkripsi salah, jalankan pipeline | `detect_layout` & Sinyal Audio tetap selesai |
| NFR-009 | Review 10 Klip hanya dengan keyboard; cek kontras dengan alat audit (axe/Lighthouse) | Bisa tanpa mouse; tidak ada pelanggaran kontras AA |
| NFR-010 | Jalankan aplikasi 2 hari (atau majukan jam sistem) | 2 file backup di `backups/`, maks. 7 disimpan |
| NFR-011 | Setelah TC-007 | Folder `segments/` kosong |
| NFR-012 | TC-024 | ≤ 120 panggilan LLM per jam stream |

### 4.2 Evaluasi kualitas (manual terukur)
Dijalankan dengan **Set Evaluasi** berisi 5 stream nyata milik Pengguna atau yang sudah diizinkan: 2 gaming Indonesia (facecam), 1 podcast Indonesia (2 orang), 1 IRL Indonesia, 1 stream berbahasa Inggris. Durasi masing-masing 1–3 jam.

| Metrik (01-prd.md bagian 3) | Cara ukur | Target |
|---|---|---|
| Kandidat relevan | Pengguna menilai 10 Kandidat Klip teratas per stream: layak/tidak | ≥ 50% layak |
| Layout tepat | Persentase Klip preset Gaming & IRL yang tidak perlu koreksi Region Cam | ≥ 80% |
| Akurasi subtitle | Hitung kata yang diedit pada 10 Klip stream Indonesia beraudio jernih | ≥ 90% kata tidak diedit |
| Kerja manual | Stopwatch dari Kandidat Klip sampai `rendered` + Paket Unggah tersalin | ≤ 3 menit/klip; ≤ 30 detik/platform untuk paket |
| Penanda live | Stopwatch dari klik "Klip 60 detik terakhir" sampai Klip bisa direview | ≤ 2 menit |

**A/B penyedia transkripsi (keputusan 07-integrasi.md INT-04):** potongan 10 menit dari tiap stream Set Evaluasi ditranskripsi oleh Deepgram dan AssemblyAI. Bandingkan: (a) persentase kata yang perlu diedit, (b) ketepatan label pembicara pada podcast, (c) akurasi deteksi bahasa, (d) waktu proses. Pemenang menjadi default `transcriber_provider`. Hasil dicatat di 07-integrasi.md (Riwayat Perubahan).

## 5. Data Uji & Lingkungan
| Data | Isi | Dipakai di |
|---|---|---|
| `fixtures/gaming_facecam_30s.mp4` | Gameplay sintetis + wajah di pojok kanan bawah (video berlisensi bebas/dibuat sendiri), ground truth Region Cam di JSON | TC-015, TC-018 |
| `fixtures/podcast_two_faces_30s.mp4` | Dua wajah kiri-kanan + audio dua pembicara | TC-019 |
| `fixtures/irl_moving_face_30s.mp4` | Satu wajah bergerak | Preset `irl` |
| `fixtures/no_face_30s.mp4`, `no_audio_10s.mp4`, `corrupt.mp4` | Kasus tepi | TC-006, TC-016, TC-039 |
| `fixtures/audio_25min_scream_at_10.flac` | Audio tenang + teriakan menit 10 | TC-011, TC-020 |
| `fixtures/live_chat_spike.jsonl` | Chat replay YouTube sintetis | TC-021 |
| `fixtures/providers/*.json` | Respons rekaman Deepgram, AssemblyAI, LLM, YouTube, TikTok, Instagram, Facebook (sukses & error) | Kontrak adapter, TC-059–TC-061 |
| Server HLS lokal | FFmpeg memutar fixture sebagai HLS "live" (`-f hls -hls_flags delete_segments`) | TC-007, TC-008, TC-064 |
| Set Evaluasi | 5 stream nyata (bagian 4.2) | Evaluasi kualitas |

Lingkungan:
- **Otomatis:** `KLIPIN_HOME` folder sementara per sesi tes, `KLIPIN_PROVIDERS=fake`, FFmpeg asli. CI GitHub Actions (ubuntu + windows) menjalankan unit, integrasi, kontrak, dan E2E headless.
- **Manual:** laptop acuan Pengguna; akun uji terpisah per platform (atau akun utama dengan visibilitas private) untuk smoke test unggah otomatis.

## 6. Kriteria Siap Rilis
- [ ] Semua TC untuk FR Must di fase yang dirilis lulus (10-roadmap.md menentukan FR per fase).
- [ ] TC-070 sampai TC-076 lulus.
- [ ] Tidak ada bug Kritis/Tinggi terbuka.
- [ ] NFR-001, NFR-002, NFR-004, NFR-005 terpenuhi di laptop acuan.
- [ ] Evaluasi kualitas (4.2) dijalankan; metrik di bawah target dicatat sebagai item roadmap, bukan penghalang rilis pribadi, kecuali akurasi subtitle < 80%.
- [ ] A/B penyedia transkripsi selesai dan default diputuskan.
- [ ] Smoke test "Tes koneksi" lulus untuk penyedia yang dipakai; jika mode otomatis termasuk rilis, satu unggahan private per platform berhasil.
- [ ] `klipin doctor` hijau di Windows dan macOS.

## Asumsi & Pertanyaan Terbuka
- [ASUMSI] Video fixture dibuat sendiri atau dari sumber berlisensi bebas, sehingga aman disimpan di repo; stream nyata Set Evaluasi tidak di-commit.
- [ASUMSI] CI tidak menjalankan tes yang memanggil API nyata; smoke test berbayar dijalankan manual.
- [ASUMSI] Laptop acuan performa = laptop Pengguna; jika spesifikasinya berbeda dari asumsi (4 core/16 GB), target NFR disesuaikan.
- [TANYA] Stream mana yang akan dipakai sebagai Set Evaluasi (perlu izin pemilik konten bila bukan milik sendiri)? (Pengguna)
- [TANYA] Apakah ada akun uji terpisah per platform untuk smoke test unggah otomatis? (Pengguna)

## Riwayat Perubahan
| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0 | 2026-11-20 | Draf awal |
| 1.1 | 2026-11-20 | Hasil CEK #1, #2: tambah TC-065 render pratinjau dan TC-066 buka folder |
