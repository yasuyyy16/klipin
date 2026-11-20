# Product Requirements Document: Klipin
> Versi 1.2 · 2026-11-20 · Status: Draf · Dokumen terkait: semua

## 1. Ringkasan
Klipin adalah aplikasi web lokal (berjalan di komputer sendiri, dibuka lewat browser di `localhost`) yang mengubah rekaman livestream YouTube dan Kick menjadi klip vertikal 9:16 siap upload. Klipin mengunduh VOD atau merekam live yang sedang berjalan. Setelah itu, Klipin mentranskripsi audio, mendeteksi posisi kamera/wajah untuk menyusun layout sesuai jenis stream (gaming, podcast, IRL, dll.), dan meranking momen yang berpotensi jadi klip berdasarkan gabungan sinyal audio, chat, dan analisis AI atas transkrip. Klip yang disetujui diberi subtitle otomatis (Indonesia/Inggris) dan dirender menjadi MP4 + .srt. Untuk tiap Klip, Pengguna memilih Mode Unggah: **manual** (Paket Unggah berisi file + caption siap salin) atau **otomatis** lewat API YouTube, TikTok, Instagram, dan Facebook. Pengguna MVP adalah satu orang: pemilik aplikasi yang membuat klip untuk dirinya sendiri.

## 2. Latar Belakang & Masalah
- Livestream biasanya berdurasi 2–8 jam. Mencari momen menarik secara manual berarti menonton ulang atau scrubbing berjam-jam.
- Setiap jenis stream butuh layout vertikal yang berbeda. Stream gaming punya facecam kecil di pojok yang harus dipindah ke atas, podcast perlu mengikuti orang yang sedang bicara, dan IRL perlu crop yang mengikuti wajah. Kalau dikerjakan manual di editor video, satu klip bisa makan 10–20 menit.
- Subtitle per kata ala TikTok/Shorts sangat berpengaruh ke retensi penonton, tetapi membuatnya manual itu lambat. Untuk stream berbahasa Inggris, subtitle juga sering perlu diterjemahkan ke Indonesia.
- Saat stream masih live, momen bagus sering lewat begitu saja karena belum ada cara cepat menandai dan memotongnya.

## 3. Tujuan & Metrik Keberhasilan
| Tujuan | Metrik | Target |
|---|---|---|
| Mempercepat pencarian momen | Waktu dari URL VOD dimasukkan sampai daftar Kandidat Klip muncul, untuk stream 3 jam | ≤ 45 menit [ASUMSI], tergantung kecepatan unduh & API |
| Kandidat yang relevan | Persentase 10 Kandidat Klip skor tertinggi yang disetujui pengguna | ≥ 50% |
| Mengurangi kerja manual | Waktu kerja aktif pengguna dari Kandidat Klip sampai Klip siap upload | ≤ 3 menit per klip |
| Layout tepat | Persentase Klip yang tidak perlu koreksi Region Cam manual | ≥ 80% untuk preset Gaming dan IRL |
| Subtitle akurat | Persentase kata subtitle yang tidak perlu diedit (stream Indonesia, audio jernih) | ≥ 90% |
| Menangkap momen saat live | Waktu dari klik "Tandai" sampai Klip dari Penanda Live bisa direview | ≤ 2 menit |
| Unggah tanpa ribet | Waktu dari Klip `rendered` sampai siap diposting manual (file + caption tersalin) | ≤ 30 detik per platform |

## 4. Pengguna & Peran
| Peran | Deskripsi | Kebutuhan utama | Perkiraan jumlah |
|---|---|---|---|
| Pengguna | Pemilik aplikasi yang menjalankan Klipin di komputernya sendiri. Satu-satunya peran; tidak ada login | Impor stream, review & edit Kandidat Klip, render, unggah manual atau otomatis ke YouTube/TikTok/Instagram/Facebook | 1 |

## 5. Ruang Lingkup
### 5.1 Termasuk (MVP)
- Impor VOD dari URL YouTube dan Kick setelah stream selesai.
- Rekam live YouTube/Kick dari URL live, pantau dengan delay pendek, dan Penanda Live manual ("Tandai mulai/selesai", "Klip N detik terakhir").
- Transkripsi otomatis lewat API cloud dengan timestamp per kata, deteksi bahasa, dan diarization (pemisahan pembicara).
- Deteksi Region Cam/wajah otomatis dan Preset Layout: Gaming, Podcast, IRL, Split Dua Orang, Crop Tengah, Kustom.
- Skor Highlight gabungan (audio + chat + analisis LLM atas transkrip) dan ranking Kandidat Klip.
- Review & edit: trim awal/akhir, ganti Preset Layout, geser Region Cam, edit teks subtitle, edit judul.
- Subtitle otomatis: Indonesia untuk stream Indonesia; untuk stream Inggris bisa pilih tampil Inggris atau terjemahan Indonesia. Tersedia beberapa Gaya Subtitle (kalimat biasa, highlight per kata).
- Render MP4 9:16 dengan subtitle ter-burn, plus file .srt.
- Unggah manual: Paket Unggah per platform (MP4, .srt, judul/caption/hashtag siap salin), lalu catat URL postingan secara manual.
- Struktur data Unggahan sudah mendukung Mode Unggah `manual` dan `auto` per platform sejak MVP (05-database.md), tetapi di MVP hanya mode `manual` yang aktif.
- Halaman Pengaturan: API key, bobot skor, folder penyimpanan, dan perkiraan durasi audio yang akan dikirim ke API sebelum Job jalan.

### 5.2 Tidak termasuk (di luar lingkup / nanti)
- Unggah otomatis (F-11, F-12): kerangka `Publisher`, OAuth per platform, dan adapter YouTube/TikTok/Instagram/Facebook dikerjakan di fase v1.1 (10-roadmap.md); prioritas Could.
- Unggah otomatis yang sudah lolos review/audit platform: Klipin tidak menjamin unggahan otomatis bisa publik. Kemungkinan dibatasi (mis. terkunci private) sampai aplikasi/project milik Pengguna lolos audit masing-masing platform.
- Penjadwalan posting (posting di jam tertentu) dan posting ke banyak akun per platform.
- Analisis otomatis bertahap selama live berlangsung (Could; lihat F-07).
- Platform selain YouTube dan Kick (Twitch, TikTok Live) sebagai sumber.
- Multi-pengguna, login, atau versi online/SaaS.
- Klip horizontal 16:9.
- Transkripsi/LLM yang berjalan lokal (offline).
- Editor video lengkap (multi-track, efek transisi, musik latar).

## 6. Fitur
| ID | Fitur | Deskripsi | Prioritas | Peran |
|---|---|---|---|---|
| F-01 | Impor VOD dari URL | Tempel URL VOD YouTube/Kick; Klipin mengunduh video + chat replay (jika tersedia) | Must | Pengguna |
| F-02 | Impor file lokal | Pilih file video dari disk sebagai Stream Sumber | Could | Pengguna |
| F-03 | Rekam & pantau live | Tempel URL live; Klipin merekam per segmen, menampilkan player near-live, dan menerima Penanda Live | Should | Pengguna |
| F-04 | Transkripsi otomatis | Kirim audio ke API transkripsi; simpan kata + timestamp + pembicara + bahasa terdeteksi | Must | Pengguna |
| F-05 | Deteksi posisi cam & Preset Layout | Deteksi wajah/Region Cam dari sampel frame, sarankan Preset Layout, bisa dikoreksi dan disimpan per kanal | Must | Pengguna |
| F-06 | Deteksi Kandidat Klip | Hitung Skor Highlight dari sinyal audio, chat, dan LLM; potong di batas kalimat; ranking | Must | Pengguna |
| F-07 | Analisis live bertahap | Saat merekam live, jalankan F-04 dan F-06 per blok (mis. tiap 5 menit) agar kandidat muncul sebelum stream selesai | Could | Pengguna |
| F-08 | Review & edit klip | Setujui/tolak Kandidat Klip, trim, ganti layout, geser Region Cam, edit subtitle & judul, dengan pratinjau | Must | Pengguna |
| F-09 | Subtitle otomatis | Bangun subtitle dari kata ber-timestamp; pilih Bahasa Tampil (asli/terjemahan Indonesia); pilih Gaya Subtitle | Must | Pengguna |
| F-10 | Render klip | Render MP4 9:16 (1080×1920) dengan layout & subtitle ter-burn, plus file .srt | Must | Pengguna |
| F-11 | Unggah otomatis YouTube | Hubungkan akun YouTube via OAuth; unggah Klip dengan judul/deskripsi/visibilitas | Could | Pengguna |
| F-12 | Unggah otomatis TikTok, Instagram, Facebook | Hubungkan akun TikTok, Instagram (Reels), dan Facebook (Reels Halaman) via OAuth; unggah Klip lewat API resmi masing-masing | Could | Pengguna |
| F-16 | Mode Unggah & unggah manual | Per Klip pilih Mode Unggah per platform: `manual` (Paket Unggah: unduh MP4 + .srt, salin caption/hashtag, buka halaman upload platform, isi URL postingan) atau `auto` (kirim ke antrean Unggahan via F-11/F-12). Default `manual` | Must | Pengguna |
| F-17 | Caption per platform | LLM membuat draf judul/caption/hashtag per platform dari transkrip Klip (mis. judul YouTube ≤ 100 karakter, caption TikTok/IG dengan hashtag); bisa diedit | Should | Pengguna |
| F-13 | Pengaturan & perkiraan pemakaian | Kelola API key, bobot Skor Highlight, folder penyimpanan; tampilkan durasi audio yang akan diproses API | Must | Pengguna |
| F-14 | Manajemen penyimpanan | Lihat ukuran file per Stream Sumber; hapus video sumber setelah selesai tanpa menghapus Klip | Should | Pengguna |
| F-15 | Pemantauan Job | Lihat progres, log singkat, coba ulang, atau batalkan Job | Must | Pengguna |

## 7. User Story Kunci
- **US-001** (F-01) Sebagai Pengguna, saya ingin menempel URL VOD YouTube atau Kick, agar videonya diproses tanpa saya mengunduh manual.
- **US-002** (F-02) Sebagai Pengguna, saya ingin memilih file video di komputer, agar rekaman yang sudah saya punya juga bisa diklip.
- **US-003** (F-03) Sebagai Pengguna, saya ingin menempel URL stream yang sedang live dan menekan "Tandai" saat ada momen seru, agar momen itu langsung jadi Kandidat Klip.
- **US-004** (F-03) Sebagai Pengguna, saya ingin tombol "Klip 60 detik terakhir", agar momen yang baru saja lewat tidak hilang.
- **US-005** (F-04) Sebagai Pengguna, saya ingin bahasa stream terdeteksi otomatis, agar saya tidak perlu mengaturnya tiap kali.
- **US-006** (F-05) Sebagai Pengguna, saya ingin memilih Preset Layout (Gaming, Podcast, IRL, dll.) dan Klipin menemukan posisi facecam sendiri, agar layout vertikal langsung rapi.
- **US-007** (F-05) Sebagai Pengguna, saya ingin koreksi Region Cam saya tersimpan per kanal, agar stream berikutnya dari streamer yang sama tidak perlu dikoreksi lagi.
- **US-008** (F-06) Sebagai Pengguna, saya ingin daftar Kandidat Klip diurutkan dari skor tertinggi beserta alasannya, agar saya bisa review yang paling menjanjikan dulu.
- **US-009** (F-08) Sebagai Pengguna, saya ingin menggeser titik awal/akhir dan mengedit teks subtitle sebelum render, agar klip tidak terpotong di tengah kalimat dan bebas salah ketik.
- **US-010** (F-09) Sebagai Pengguna, untuk stream berbahasa Inggris saya ingin memilih subtitle Inggris atau terjemahan Indonesia, agar sesuai target penonton.
- **US-011** (F-09) Sebagai Pengguna, saya ingin subtitle highlight per kata, agar klip terlihat seperti konten Shorts/TikTok.
- **US-012** (F-10) Sebagai Pengguna, saya ingin hasil render berupa MP4 9:16 dan file .srt, agar bisa saya unggah manual ke platform mana pun.
- **US-013** (F-11) Sebagai Pengguna, saya ingin mengunggah Klip ke YouTube langsung dari Klipin, agar tidak perlu membuka YouTube Studio.
- **US-016** (F-12) Sebagai Pengguna, saya ingin menghubungkan akun TikTok, Instagram, dan Facebook, agar satu Klip bisa diposting ke beberapa platform sekaligus tanpa membuka aplikasinya satu per satu.
- **US-017** (F-16) Sebagai Pengguna, saya ingin memilih unggah manual atau otomatis per platform, agar platform yang API-nya belum bisa dipakai tetap bisa saya posting sendiri.
- **US-018** (F-16) Sebagai Pengguna, saat unggah manual saya ingin file dan caption sudah siap salin serta bisa mencatat link postingannya, agar riwayat Klip yang sudah diposting tetap rapi.
- **US-019** (F-17) Sebagai Pengguna, saya ingin draf caption & hashtag dibuat otomatis sesuai gaya tiap platform, agar tidak menulis ulang untuk setiap platform.
- **US-014** (F-13) Sebagai Pengguna, saya ingin melihat perkiraan menit audio yang akan dikirim ke API sebelum memproses, agar biaya API terkendali.
- **US-015** (F-15) Sebagai Pengguna, saya ingin Job yang gagal bisa dicoba ulang dari tahap yang gagal, agar tidak perlu mengunduh ulang stream 6 jam.

## 8. Kamus Istilah
Sumber kebenaran untuk nama entitas, peran, dan status. Semua dokumen lain WAJIB memakai nama ini.

| Istilah | Jenis | Definisi | Nama teknis |
|---|---|---|---|
| Pengguna | Peran | Satu-satunya pemakai Klipin, pemilik komputer tempat Klipin berjalan | `user` (tidak ada tabel) |
| Stream Sumber | Entitas | Satu video sumber: VOD dari URL, rekaman live, atau file lokal | `source_streams` |
| Jenis Sumber | Konsep | Asal Stream Sumber: `vod_url`, `live_url`, `local_file` | `source_streams.source_type` |
| Platform | Konsep | Asal URL: `youtube`, `kick`, `local` | `source_streams.platform` |
| Kanal | Entitas | Kanal/streamer pemilik stream; menyimpan Preset Layout dan Region Cam default | `channels` |
| Job | Entitas | Satu unit kerja latar belakang pada Stream Sumber atau Klip | `jobs` |
| Jenis Job | Konsep | `download`, `record_live`, `transcribe`, `detect_layout`, `score_highlights`, `render`, `upload` | `jobs.job_type` |
| Segmen Transkrip | Entitas | Satu kalimat/ujaran hasil transkripsi, berisi pembicara, waktu mulai/selesai, bahasa | `transcript_segments` |
| Kata Transkrip | Entitas | Satu kata dengan timestamp mulai/selesai; dasar subtitle per kata | `transcript_words` |
| Pesan Chat | Entitas | Satu pesan chat replay dengan timestamp relatif terhadap video | `chat_messages` |
| Sinyal | Konsep | Masukan untuk skor: Sinyal Audio (lonjakan volume/tawa), Sinyal Chat (lonjakan pesan), Sinyal LLM (penilaian transkrip) | — |
| Skor Highlight | Konsep | Nilai 0–100 gabungan berbobot dari Sinyal untuk satu rentang waktu | `clips.score` |
| Kandidat Klip | Status/Konsep | Klip berstatus `candidate`: rentang waktu yang diusulkan sistem atau Penanda Live, belum direview | `clips.status = candidate` |
| Klip | Entitas | Rentang waktu dari Stream Sumber beserta layout, subtitle, judul, dan hasil render | `clips` |
| Penanda Live | Entitas | Titik/rentang yang ditandai Pengguna saat merekam live | `live_markers` |
| Preset Layout | Entitas | Aturan menyusun frame 9:16: `gaming`, `podcast`, `irl`, `split_two`, `center_crop`, `custom` | `layout_presets` |
| Region Cam | Entitas | Kotak koordinat (x, y, lebar, tinggi, relatif 0–1) area kamera/wajah atau area konten (gameplay) di frame sumber | `cam_regions` |
| Gaya Subtitle | Entitas | Template tampilan subtitle: font, ukuran, warna, posisi, mode (`sentence` / `word_highlight`) | `subtitle_styles` |
| Bahasa Tampil | Konsep | Bahasa subtitle yang ditampilkan di Klip: `source` (asli) atau `id` (terjemahan Indonesia) | `clips.subtitle_language` |
| Platform Tujuan | Konsep | Platform tempat Klip diposting: `youtube`, `tiktok`, `instagram`, `facebook` | `upload_accounts.platform`, `uploads.platform` |
| Akun Unggah | Entitas | Akun pada satu Platform Tujuan yang terhubung via OAuth, beserta token tersimpan (hanya untuk Mode Unggah `auto`) | `upload_accounts` |
| Mode Unggah | Konsep | Cara memposting Klip ke satu Platform Tujuan: `manual` (Pengguna memposting sendiri dari Paket Unggah) atau `auto` (Klipin memposting lewat API) | `uploads.mode` |
| Paket Unggah | Konsep | Kumpulan siap-posting untuk satu Platform Tujuan: file MP4, .srt, judul/caption, hashtag, dan tautan halaman upload platform | — (dihasilkan dari `clips` + `uploads`) |
| Unggahan | Entitas | Satu catatan posting satu Klip ke satu Platform Tujuan, baik manual maupun otomatis | `uploads` |
| Status Stream Sumber | Status | `queued`, `downloading`, `recording`, `processing`, `ready`, `failed` | `source_streams.status` |
| Status Job | Status | `queued`, `running`, `succeeded`, `failed`, `cancelled` | `jobs.status` |
| Status Klip | Status | `candidate`, `approved`, `rejected`, `rendering`, `rendered`, `render_failed` | `clips.status` |
| Status Unggahan | Status | `pending`, `uploading`, `uploaded`, `failed`. Mode `manual`: `pending` (Paket Unggah dibuat) → `uploaded` (Pengguna menandai sudah diposting, URL opsional) | `uploads.status` |

## 9. Batasan & Risiko
| Risiko | Dampak | Kemungkinan | Mitigasi |
|---|---|---|---|
| Hak cipta & ToS platform: mengunduh/mengklip stream milik orang lain bisa melanggar ToS YouTube/Kick atau hak cipta pemilik konten | Tinggi (klip di-takedown, strike akun) | Sedang | Pengguna bertanggung jawab memastikan izin (stream sendiri atau ada izin klipper). Tampilkan pengingat saat impor. Ini bukan nasihat hukum |
| yt-dlp rusak karena perubahan situs YouTube/Kick | Tinggi (impor gagal) | Tinggi (sering terjadi) | yt-dlp dipasang sebagai dependensi yang mudah di-update; tombol "Perbarui yt-dlp" di Pengaturan; pesan error jelas |
| Chat replay Kick tidak bisa diambil | Sedang (skor kurang akurat) | Sedang | Skor tetap jalan tanpa Sinyal Chat; bobot dibagi ulang (BR di 02-requirements.md) |
| Biaya API transkripsi/LLM membengkak untuk stream panjang | Sedang | Sedang | Perkiraan durasi audio sebelum Job; LLM hanya menilai jendela yang lolos pra-seleksi audio/chat; batas durasi per Job di Pengaturan |
| Unggah via API YouTube dari project yang belum lolos audit dikunci private (dicek di 07-integrasi.md) | Sedang (F-11 terbatas) | Tinggi | F-11 diturunkan ke Could; Mode Unggah `manual` (F-16) sebagai jalur utama; audit opsional |
| API TikTok, Instagram, dan Facebook butuh aplikasi developer milik Pengguna, jenis akun tertentu, dan review/audit sebelum bisa memposting publik. Ketentuannya bisa berubah | Sedang (F-12 terbatas/tertunda) | Tinggi | F-12 berprioritas Could; adapter per platform; Mode Unggah `manual` selalu tersedia; ketentuan terbaru dicek di 07-integrasi.md |
| Token OAuth beberapa platform kedaluwarsa/dicabut | Rendah | Sedang | Status Akun Unggah ditampilkan di Pengaturan; Unggahan `failed` dengan pesan hubungkan ulang; fallback manual |
| Deteksi wajah salah (avatar/VTuber, cam gelap, banyak wajah) | Sedang | Sedang | Region Cam bisa dikoreksi manual dan disimpan per Kanal; preset `center_crop` sebagai fallback |
| Disk penuh karena VOD berjam-jam | Sedang | Sedang | Tampilkan ukuran file, cek ruang kosong sebelum unduh, F-14 hapus sumber |
| Proses berat membuat komputer lambat | Rendah | Sedang | Worker 1 Job berat sekaligus (bisa diatur); render pakai preset FFmpeg cepat |

## Asumsi & Pertanyaan Terbuka
- [ASUMSI] Nama produk sementara "Klipin".
- [ASUMSI] Pembangun aplikasi solo dan nyaman dengan Python.
- [ASUMSI] Berjalan di satu PC/laptop Windows atau macOS tanpa wajib GPU; FFmpeg terpasang.
- [ASUMSI] Durasi Stream Sumber maksimal ±8 jam; durasi Klip 15–90 detik.
- [ASUMSI] Pengguna hanya mengklip stream miliknya sendiri atau yang sudah diizinkan pemiliknya.
- [ASUMSI] Target metrik di bagian 3 adalah perkiraan awal dan akan dikalibrasi setelah uji dengan stream nyata.
- [TERJAWAB] Penyedia transkripsi: default Deepgram, alternatif AssemblyAI; final setelah uji A/B (07-integrasi.md INT-04, 09-testing.md §4.2).
- [TANYA] Apakah VTuber/avatar perlu didukung di preset Gaming? (Pengguna)
- [TANYA] Apakah chat replay Kick bisa diambil secara andal? Perlu uji teknis.
- [ASUMSI] Facebook yang dimaksud adalah Reels di **Halaman (Page)** Facebook milik Pengguna; API resmi Meta umumnya untuk Halaman, bukan profil pribadi. Perlu dikonfirmasi di 07-integrasi.md.
- [ASUMSI] Instagram yang dimaksud adalah akun Professional (Business/Creator) yang bisa dihubungkan ke API Meta.
- [ASUMSI] Satu Akun Unggah per Platform Tujuan sudah cukup.
- [TANYA] Urutan prioritas integrasi otomatis antar platform? Default di 10-roadmap.md: TikTok → Instagram → Facebook → YouTube. (Pengguna)

## Riwayat Perubahan
| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0 | 2026-11-20 | Draf awal |
| 1.2 | 2026-11-20 | Hasil CEK #5, #11: lingkup MVP diselaraskan dengan 10-roadmap.md (MVP hanya unggah manual; kerangka & adapter unggah otomatis di v1.1); pertanyaan penyedia transkripsi ditandai terjawab |
| 1.1 | 2026-11-20 | F-11 Unggah otomatis YouTube jadi Could; F-12 diperluas ke TikTok, Instagram, Facebook (Could); tambah F-16 Mode Unggah & unggah manual (Must) dan F-17 caption per platform (Should); tambah US-016–US-019; Kamus Istilah: Platform Tujuan, Mode Unggah, Paket Unggah; risiko API platform |
