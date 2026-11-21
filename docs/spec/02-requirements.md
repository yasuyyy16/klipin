# Spesifikasi Kebutuhan: Klipin
> Versi 1.3 · 2026-11-21 · Status: Draf · Dokumen terkait: 01-prd.md, 07-integrasi.md

## 1. Kebutuhan Fungsional
Semua FR dijalankan oleh peran **Pengguna** (satu-satunya peran). Istilah mengikuti Kamus Istilah di 01-prd.md.

### Impor & Rekam

### FR-001 Impor VOD dari URL
- **Fitur/Story:** F-01, US-001
- **Peran:** Pengguna
- **Deskripsi:** Pengguna menempel URL VOD YouTube atau Kick. Sistem memvalidasi URL, mengambil metadata (judul, Kanal, durasi), membuat Stream Sumber (`source_type = vod_url`), lalu membuat Job `download` yang mengunduh video (maks. 1080p) dan chat replay jika tersedia.
- **Kriteria penerimaan:**
  - [ ] Given URL VOD YouTube yang valid dan publik, when Pengguna menekan "Impor", then dalam ≤ 10 detik tampil metadata (judul, Kanal, durasi), Stream Sumber dibuat berstatus `queued`, dan Job `download` masuk antrean.
  - [ ] Given Job `download` selesai, when file video dan (jika ada) chat replay tersimpan, then Status Stream Sumber menjadi `processing` dan Job `transcribe` serta `detect_layout` otomatis dibuat.
  - [ ] Given URL yang bukan YouTube/Kick atau bukan video, when Pengguna menekan "Impor", then tampil pesan "URL tidak dikenali. Gunakan link VOD YouTube atau Kick." dan tidak ada Stream Sumber dibuat.
  - [ ] Given URL yang merujuk stream yang masih live, when Pengguna memilih "Impor VOD", then sistem menyarankan "Stream ini masih live. Gunakan Rekam Live?" (FR-003).
  - [ ] Given ruang disk kosong < perkiraan ukuran unduhan × 1,5, when Pengguna menekan "Impor", then impor ditolak dengan pesan berisi ruang yang dibutuhkan dan yang tersedia.

### FR-002 Impor file lokal
- **Fitur/Story:** F-02, US-002
- **Peran:** Pengguna
- **Deskripsi:** Pengguna memilih file video (mp4, mkv, mov, webm) dari disk. Sistem menyalin atau mereferensikan file sesuai Pengaturan, membuat Stream Sumber (`source_type = local_file`, `platform = local`), lalu langsung menjadwalkan `transcribe` dan `detect_layout`.
- **Kriteria penerimaan:**
  - [ ] Given file mp4 yang valid, when dipilih, then Stream Sumber dibuat dengan durasi yang dibaca FFprobe dan Job `transcribe` + `detect_layout` masuk antrean.
  - [ ] Given file tanpa trek audio, when dipilih, then tampil pesan "Video tidak memiliki audio, transkripsi tidak bisa dilakukan." dan Stream Sumber tidak dibuat.

### FR-003 Rekam live dari URL
- **Fitur/Story:** F-03, US-003
- **Peran:** Pengguna
- **Deskripsi:** Pengguna menempel URL live YouTube/Kick. Sistem membuat Stream Sumber (`source_type = live_url`, status `recording`) dan Job `record_live` yang merekam HLS ke file segmen berdurasi tetap (default 10 detik). Rekaman berhenti saat stream berakhir atau Pengguna menekan "Berhenti Rekam". Setelah berhenti, segmen digabung menjadi satu file dan pipeline VOD (FR-005 dst.) dijalankan.
- **Kriteria penerimaan:**
  - [ ] Given URL live yang sedang berjalan, when Pengguna menekan "Mulai Rekam", then dalam ≤ 30 detik segmen pertama tersimpan dan player near-live di P-03 mulai memutar.
  - [ ] Given rekaman berjalan, when koneksi putus < 60 detik, then Job mencoba menyambung ulang dan rekaman berlanjut; celah waktu dicatat di log Job.
  - [ ] Given stream berakhir atau Pengguna menekan "Berhenti Rekam", when segmen terakhir tersimpan, then segmen digabung, Status Stream Sumber menjadi `processing`, dan Job `transcribe` + `detect_layout` dibuat.
  - [ ] Given URL yang bukan stream live, when Pengguna menekan "Mulai Rekam", then tampil pesan "Stream ini tidak sedang live. Gunakan Impor VOD."

### FR-004 Penanda Live
- **Fitur/Story:** F-03, US-003, US-004
- **Peran:** Pengguna
- **Deskripsi:** Saat merekam, Pengguna dapat (a) menekan "Tandai Mulai" lalu "Tandai Selesai", atau (b) menekan "Klip N detik terakhir" (N default 60, bisa diatur 15–90). Setiap aksi membuat Penanda Live dan langsung membuat Klip berstatus `candidate` (`origin = live_marker`) yang bisa direview sebelum stream selesai, memakai potongan dari segmen yang sudah terekam.
- **Kriteria penerimaan:**
  - [ ] Given rekaman berjalan ≥ 60 detik, when Pengguna menekan "Klip 60 detik terakhir", then Penanda Live dibuat dengan rentang [waktu_sekarang − 60 detik, waktu_sekarang] menurut timeline rekaman, dan Kandidat Klip muncul di daftar dalam ≤ 2 menit (termasuk transkripsi potongan tersebut).
  - [ ] Given "Tandai Mulai" ditekan, when "Tandai Selesai" ditekan > 90 detik kemudian, then Klip tetap dibuat, diberi peringatan "Durasi melebihi 90 detik", dan wajib di-trim sebelum disetujui (BR-004).
  - [ ] Given rekaman baru berjalan 20 detik, when "Klip 60 detik terakhir" ditekan, then rentang dipotong menjadi [0, 20 detik] dan tampil info "Rekaman baru 20 detik".

### Transkripsi & Layout

### FR-005 Transkripsi otomatis
- **Fitur/Story:** F-04, US-005
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Job `transcribe` mengekstrak audio (mono, 16 kHz) dengan FFmpeg, membaginya menjadi potongan ≤ batas ukuran API, lalu mengirimnya ke API transkripsi dengan opsi timestamp per kata, deteksi bahasa, dan diarization. Hasil disimpan sebagai Segmen Transkrip dan Kata Transkrip dengan waktu absolut terhadap Stream Sumber. Bahasa dominan disimpan di `source_streams.detected_language`.
- **Kriteria penerimaan:**
  - [ ] Given Stream Sumber 3 jam berbahasa Indonesia, when Job `transcribe` selesai, then Kata Transkrip tersimpan dengan `start_ms` < `end_ms`, berurutan naik, tanpa celah > 2 detik di sambungan antar potongan audio, dan `detected_language = id`.
  - [ ] Given API mengembalikan error sementara (timeout/5xx/429), when terjadi pada satu potongan, then hanya potongan itu yang dicoba ulang (maks. 3 kali, backoff 2/4/8 detik); potongan yang sudah berhasil tidak dikirim ulang.
  - [ ] Given API key transkripsi kosong/tidak valid, when Job dijalankan, then Job `failed` dengan pesan "API key transkripsi belum diisi atau tidak valid. Buka Pengaturan." tanpa mengirim audio.
  - [ ] Given potongan audio hening total, when dikirim, then tidak membuat Kata Transkrip kosong dan Job tetap `succeeded`.

### FR-006 Deteksi Region Cam & saran Preset Layout
- **Fitur/Story:** F-05, US-006, US-007
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Job `detect_layout` mengambil sampel frame (default 1 frame per 10 detik, maks. 600 frame), menjalankan deteksi wajah lokal, dan mengelompokkan posisi wajah. Aturannya: jika wajah dominan konsisten berada di area kecil (< 25% luas frame) yang posisinya stabil, sistem menyarankan preset `gaming` dan menyimpan Region Cam (`role = cam`) + Region Cam area konten (`role = content`). Jika ada 2+ wajah stabil, sistem menyarankan `podcast`/`split_two`. Jika wajah besar dan bergerak, sistem menyarankan `irl`. Jika tidak ada wajah, `center_crop`. Jika Kanal sudah punya Preset Layout & Region Cam tersimpan, simpanan Kanal dipakai dan deteksi hanya memverifikasi.
- **Kriteria penerimaan:**
  - [ ] Given VOD gaming dengan facecam tetap di pojok kanan bawah, when Job selesai, then preset tersaran `gaming` dan Region Cam `cam` beririsan ≥ 80% (IoU ≥ 0,8) dengan area facecam sebenarnya pada data uji.
  - [ ] Given Kanal dengan Region Cam tersimpan, when Stream Sumber baru dari Kanal itu diproses, then Region Cam tersimpan dipakai tanpa koreksi manual.
  - [ ] Given tidak ada wajah terdeteksi di ≥ 90% sampel, when Job selesai, then preset tersaran `center_crop` dan UI menampilkan "Wajah tidak terdeteksi. Tandai area kamera manual jika ada."

### FR-007 Layout per Preset Layout
- **Fitur/Story:** F-05, US-006
- **Peran:** Pengguna
- **Deskripsi:** Sistem menyusun frame 1080×1920 sesuai preset:
  - `gaming`: Region Cam `cam` di atas (tinggi default 35%), area `content` di bawah (65%), keduanya di-scale dan di-crop agar penuh.
  - `irl`: crop 9:16 yang mengikuti pusat wajah; posisi crop dihaluskan (perpindahan maks. 5% lebar frame per detik) agar tidak goyang.
  - `podcast`: crop 9:16 ke wajah pembicara aktif. Pembicara ditentukan dari diarization yang dipetakan ke wajah; perpindahan crop minimal tertahan 1,5 detik.
  - `split_two`: dua wajah utama ditumpuk atas–bawah (50/50).
  - `center_crop`: crop tengah 9:16.
  - `custom`: Pengguna menggambar 1–2 Region Cam beserta urutan tumpukannya.
- **Kriteria penerimaan:**
  - [ ] Given preset `gaming` dan Region Cam valid, when pratinjau dibuat, then frame output 1080×1920 menampilkan facecam di 35% atas dan konten di 65% bawah tanpa bar hitam.
  - [ ] Given preset `podcast` dan dua pembicara bergantian setiap 0,5 detik, when dirender, then crop tidak berpindah lebih cepat dari sekali per 1,5 detik.
  - [ ] Given Pengguna mengganti preset di P-05, when pratinjau diperbarui, then pratinjau frame tampil dalam ≤ 3 detik.

### FR-008 Simpan koreksi layout per Kanal
- **Fitur/Story:** F-05, US-007
- **Peran:** Pengguna
- **Deskripsi:** Saat Pengguna mengoreksi Region Cam/preset, tersedia pilihan "Simpan sebagai default Kanal ini". Simpanan dipakai FR-006 untuk Stream Sumber berikutnya dari Kanal yang sama.
- **Kriteria penerimaan:**
  - [ ] Given Pengguna mencentang "Simpan sebagai default Kanal ini", when menyimpan, then `channels.default_layout_preset_id` dan Region Cam default Kanal terisi, dan Klip lain dari Stream Sumber yang sama yang belum dirender ikut diperbarui jika Pengguna memilih "Terapkan ke semua klip".
  - [ ] Given Stream Sumber dari file lokal (tanpa Kanal), when Pengguna memilih simpan default, then Pengguna diminta memilih atau membuat Kanal terlebih dulu.

### Highlight

### FR-009 Hitung Sinyal Audio
- **Fitur/Story:** F-06, US-008
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Bagian dari Job `score_highlights`. Sistem menghitung loudness (RMS/LUFS) per jendela 1 detik, lalu menormalkannya per Stream Sumber (z-score). Lonjakan, yaitu kenaikan ≥ 2 standar deviasi terhadap rata-rata 60 detik sebelumnya, menjadi Sinyal Audio bernilai 0–1.
- **Kriteria penerimaan:**
  - [ ] Given audio uji dengan teriakan yang disisipkan pada menit 10, when dihitung, then jendela menit 10 memiliki Sinyal Audio ≥ 0,8 dan jendela tenang < 0,3.

### FR-010 Hitung Sinyal Chat
- **Fitur/Story:** F-06, US-008
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Jika Pesan Chat tersedia, sistem menghitung jumlah pesan per jendela 10 detik, dinormalkan terhadap median 5 menit sekitarnya. Pesan berisi kata/emote reaksi (mis. "wkwk", "KEKW", "LOL", "anjir", "gg") diberi bobot 1,5×. Daftar kata reaksi bisa diedit di Pengaturan. Karena chat tertinggal dari kejadian, Sinyal Chat digeser mundur sebesar Jeda Chat (default 8 detik).
- **Kriteria penerimaan:**
  - [ ] Given chat replay dengan lonjakan 5× median pada detik 600, when dihitung, then Sinyal Chat tertinggi berada pada jendela ±10 detik dari detik 592.
  - [ ] Given Stream Sumber tanpa Pesan Chat, when skor dihitung, then Sinyal Chat ditandai "tidak tersedia" dan BR-002 berlaku.

### FR-011 Hitung Sinyal LLM
- **Fitur/Story:** F-06, US-008
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Untuk menghemat biaya, LLM hanya menilai jendela yang lolos pra-seleksi (BR-003). Setiap jendela dikirim sebagai transkrip ±90 detik (dengan label pembicara). LLM mengembalikan JSON: skor 0–100, kategori (`lucu`, `hype`, `kontroversial`, `informatif`, `emosional`, `lainnya`), alasan singkat (≤ 20 kata, bahasa Indonesia), saran rentang mulai–selesai yang berada di batas kalimat, dan saran judul (≤ 60 karakter).
- **Kriteria penerimaan:**
  - [ ] Given jendela lolos pra-seleksi, when dinilai, then respons LLM tervalidasi terhadap skema JSON; respons tidak valid dicoba ulang 1 kali, lalu jendela diberi Sinyal LLM = null (bukan 0) dan dicatat di log.
  - [ ] Given saran rentang dari LLM di luar jendela atau durasinya < 15 detik / > 90 detik, when diproses, then rentang dikoreksi sesuai BR-004.

### FR-012 Gabung skor & buat Kandidat Klip
- **Fitur/Story:** F-06, US-008
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Sistem menghitung Skor Highlight per jendela sesuai BR-001/BR-002, memilih jendela terbaik dengan aturan non-overlap (BR-005), lalu membuat Klip berstatus `candidate` (`origin = auto`) beserta skor, rincian Sinyal, kategori, alasan, dan saran judul. Jumlah kandidat mengikuti BR-006.
- **Kriteria penerimaan:**
  - [ ] Given Stream Sumber 3 jam selesai diproses, when Job `score_highlights` selesai, then terbentuk 1–20 Kandidat Klip, masing-masing berdurasi 15–90 detik, tidak saling tumpang tindih > 5 detik, diurutkan dari Skor Highlight tertinggi.
  - [ ] Given Kandidat Klip ditampilkan, when Pengguna membuka rinciannya, then terlihat nilai tiap Sinyal (atau "tidak tersedia"), kategori, dan alasan.
  - [ ] Given Pengguna menekan "Hitung ulang skor" setelah mengubah bobot, when selesai, then Kandidat Klip `origin = auto` yang masih `candidate` diganti; Klip `approved`/`rendered` dan Klip dari Penanda Live tidak berubah.

### FR-013 Analisis live bertahap
- **Fitur/Story:** F-07
- **Peran:** Pengguna (dipicu otomatis)
- **Deskripsi:** Jika opsi "Analisis selama live" aktif, setiap blok rekaman (default 5 menit) yang selesai dijalankan melalui `transcribe` dan `score_highlights` khusus blok tersebut. Kandidat Klip baru muncul di P-03 selama rekaman berlangsung.
- **Kriteria penerimaan:**
  - [ ] Given opsi aktif dan rekaman berjalan 12 menit, when dua blok pertama selesai, then Kandidat Klip dari menit 0–10 (jika ada) sudah tampil di P-03 sebelum rekaman berhenti.
  - [ ] Given rekaman berhenti, when pipeline penuh berjalan, then Kata Transkrip blok yang sudah diproses tidak dikirim ulang ke API.

### Review, Subtitle, Render, Unggah

### FR-014 Review Kandidat Klip
- **Fitur/Story:** F-08, US-008, US-009
- **Peran:** Pengguna
- **Deskripsi:** Pengguna melihat daftar Klip per Stream Sumber (filter status, urut skor/waktu), memutar pratinjau 9:16, lalu menekan "Setujui" atau "Tolak". Pengguna juga dapat menambah Klip manual dengan memilih rentang di timeline.
- **Kriteria penerimaan:**
  - [ ] Given Kandidat Klip, when Pengguna menekan "Setujui", then Status Klip menjadi `approved`; when menekan "Tolak", then menjadi `rejected` dan tersembunyi dari filter default.
  - [ ] Given Klip `rejected`, when Pengguna memilih "Pulihkan", then status kembali `candidate`.
  - [ ] Given Pengguna memilih rentang 40 detik di timeline dan menekan "Buat Klip", then Klip baru `candidate` (`origin = manual`) dibuat lengkap dengan subtitle dari Kata Transkrip yang ada.

### FR-015 Edit Klip
- **Fitur/Story:** F-08, US-009
- **Peran:** Pengguna
- **Deskripsi:** Di editor (P-05), Pengguna dapat: trim awal/akhir (langkah 0,1 detik, tombol "jepret ke batas kalimat"), mengganti Preset Layout, menggeser/mengubah ukuran Region Cam, mengedit teks per kata/baris subtitle, memilih Gaya Subtitle, memilih Bahasa Tampil, dan mengedit judul. Perubahan disimpan otomatis.
- **Kriteria penerimaan:**
  - [ ] Given Pengguna menggeser titik akhir, when "jepret ke batas kalimat" aktif, then titik akhir pindah ke akhir Segmen Transkrip terdekat (± 2 detik).
  - [ ] Given Pengguna mengedit kata "gua" menjadi "gue" pada subtitle, when Klip dirender, then hasil render dan .srt memuat "gue", sedangkan Kata Transkrip asli tidak berubah (edit disimpan di level Klip).
  - [ ] Given Klip berstatus `rendered`, when Pengguna mengeditnya, then status kembali `approved` dan tampil info "Perlu render ulang".

### FR-016 Bangun subtitle & pilih bahasa
- **Fitur/Story:** F-09, US-010, US-011
- **Peran:** Pengguna
- **Deskripsi:** Subtitle Klip dibangun dari Kata Transkrip dalam rentang Klip, dikelompokkan per baris (maks. 3 kata untuk `word_highlight`, maks. 42 karakter untuk `sentence`). Bahasa Tampil default: `source`. Jika `detected_language = en`, Pengguna dapat memilih `id`. Sistem lalu menerjemahkan baris lewat LLM. Karena terjemahan tidak punya timestamp per kata, terjemahan selalu memakai mode `sentence` dengan timestamp baris asli (BR-008).
- **Kriteria penerimaan:**
  - [ ] Given stream Indonesia, when Klip dibuat, then subtitle berbahasa Indonesia dan opsi terjemahan tidak ditampilkan.
  - [ ] Given stream Inggris dan Pengguna memilih Bahasa Tampil "Indonesia", when terjemahan selesai (≤ 30 detik untuk Klip 60 detik), then pratinjau menampilkan teks Indonesia dengan waktu baris yang sama dengan baris Inggris asli.
  - [ ] Given terjemahan gagal setelah 2 kali coba, when terjadi, then Bahasa Tampil kembali ke `source` dan tampil pesan "Terjemahan gagal, subtitle memakai bahasa asli."

### FR-017 Gaya Subtitle
- **Fitur/Story:** F-09, US-011
- **Peran:** Pengguna
- **Deskripsi:** Tersedia minimal 3 Gaya Subtitle bawaan: "Sederhana" (`sentence`, putih ber-outline), "Highlight Kata" (`word_highlight`, kata aktif berwarna kuning), dan "Besar Tengah" (`word_highlight`, 1–2 kata, huruf besar). Pengguna dapat menggandakan dan mengubah font, ukuran, warna, outline, serta posisi vertikal (persen dari atas).
- **Kriteria penerimaan:**
  - [ ] Given Gaya "Highlight Kata", when dirender, then setiap kata berubah warna tepat pada `start_ms` kata itu (toleransi ±100 ms).
  - [ ] Given preset `gaming`, when Gaya Subtitle dipakai dengan posisi default, then subtitle berada di batas area cam–konten dan tidak menutupi wajah di Region Cam.

### FR-018 Render Klip
- **Fitur/Story:** F-10, US-012
- **Peran:** Pengguna
- **Deskripsi:** Pengguna menekan "Render" pada satu Klip atau "Render semua yang disetujui". Sistem membuat Job `render` per Klip: memotong rentang, menyusun layout, membakar subtitle (file ASS) dengan FFmpeg, menghasilkan MP4 H.264/AAC 1080×1920 30 fps, plus file .srt sesuai Bahasa Tampil. Nama file: `{tanggal}_{kanal}_{judul-slug}.mp4`.
- **Kriteria penerimaan:**
  - [ ] Given Klip `approved` berdurasi 60 detik, when Job `render` selesai, then file MP4 1080×1920 dan .srt tersimpan di folder output, Status Klip `rendered`, dan durasi MP4 = durasi Klip ± 0,1 detik.
  - [ ] Given render gagal (mis. FFmpeg error), when terjadi, then Status Klip `render_failed`, pesan error FFmpeg (baris terakhir) tampil, dan tombol "Coba lagi" tersedia.
  - [ ] Given Klip berstatus `candidate`, when Pengguna mencoba render, then render ditolak dengan pesan "Setujui klip dulu sebelum render." (BR-007).

### FR-019 Hubungkan Akun Unggah (YouTube, TikTok, Instagram, Facebook)
- **Fitur/Story:** F-11, F-12, US-013, US-016
- **Peran:** Pengguna
- **Deskripsi:** Di Pengaturan tab "Akun Unggah", setiap Platform Tujuan punya tombol "Hubungkan". Sistem menjalankan OAuth 2.0 penyedia (Google untuk YouTube, TikTok untuk TikTok, Meta untuk Instagram & Facebook) dengan redirect ke `http://localhost:{port}/oauth/callback/{platform}` (`KLIPIN_OAUTH_REDIRECT_BASE`, lihat 07-integrasi.md) dan scope minimum untuk memposting. Token disimpan di keyring OS. Untuk Facebook, Pengguna memilih Halaman tujuan; untuk Instagram, akun Professional yang terhubung. Tombol "Hubungkan" platform hanya aktif jika kredensial aplikasi developer platform itu sudah diisi di konfigurasi; jika belum, tampil panduan singkat. Satu Akun Unggah aktif per Platform Tujuan.
- **Kriteria penerimaan:**
  - [ ] Given kredensial aplikasi developer TikTok terisi dan Pengguna menyetujui izin, when callback diterima, then Akun Unggah `tiktok` tersimpan dan nama akunnya tampil di Pengaturan.
  - [ ] Given Pengguna menghubungkan Facebook dan memiliki 2 Halaman, when izin disetujui, then Pengguna diminta memilih satu Halaman sebelum Akun Unggah disimpan.
  - [ ] Given kredensial aplikasi developer Meta belum diisi, when Pengguna membuka tab Akun Unggah, then tombol Instagram & Facebook nonaktif dengan teks "Isi kredensial aplikasi Meta dulu (lihat panduan)."
  - [ ] Given Pengguna menekan "Putuskan" pada satu platform, when dikonfirmasi, then token platform itu dicabut (jika platform menyediakan endpoint pencabutan) dan dihapus dari keyring; platform lain tidak terpengaruh.
  - [ ] Given token kedaluwarsa/dicabut, when Job `upload` berjalan, then Job `failed` dengan pesan "Koneksi {Platform} kedaluwarsa. Hubungkan ulang di Pengaturan." dan Akun Unggah ditandai bermasalah.

### FR-020 Unggah otomatis
- **Fitur/Story:** F-11, F-12, US-013, US-016
- **Peran:** Pengguna
- **Deskripsi:** Di dialog unggah Klip `rendered`, Pengguna mencentang satu atau lebih Platform Tujuan dengan Mode Unggah `auto`, meninjau judul/caption/hashtag/visibilitas per platform, lalu menekan "Kirim". Sistem membuat satu Unggahan (`mode = auto`, `pending`) dan satu Job `upload` per platform. Adapter platform mengunggah file (resumable/chunked bila didukung), menunggu status publikasi selesai bila platform memprosesnya secara asinkron, lalu menyimpan ID & URL postingan. Batasan tiap platform (durasi, ukuran, visibilitas yang diizinkan untuk aplikasi belum diaudit) diambil dari konfigurasi adapter (07-integrasi.md).
- **Kriteria penerimaan:**
  - [ ] Given Klip `rendered` dan Akun Unggah YouTube & TikTok terhubung, when Pengguna memilih keduanya dengan mode `auto` dan menekan "Kirim", then terbentuk 2 Unggahan dan 2 Job `upload` yang berjalan terpisah; kegagalan satu tidak membatalkan yang lain.
  - [ ] Given Unggahan selesai, when platform mengonfirmasi publikasi, then Status Unggahan `uploaded` dan URL postingan tampil dan bisa diklik.
  - [ ] Given visibilitas yang dipilih tidak diizinkan untuk aplikasi Pengguna (mis. publik pada project belum diaudit), when dialog dibuka, then opsi itu dinonaktifkan dengan keterangan, atau setelah unggah tampil peringatan "Diposting sebagai private oleh platform".
  - [ ] Given Klip melanggar batas platform (mis. durasi/ukuran), when Pengguna mencentang platform itu, then muncul pesan validasi dan platform tidak bisa dipilih untuk `auto` (mode `manual` tetap bisa).
  - [ ] Given koneksi putus di tengah unggah, when tersambung lagi, then unggah dilanjutkan bila platform mendukung resumable, maksimal 3 kali sebelum `failed`.
  - [ ] Given Unggahan `failed`, when Pengguna menekan "Unggah manual saja", then dibuat Unggahan baru `mode = manual` untuk platform yang sama (FR-025).

### Pengaturan & Operasional

### FR-021 Pengaturan
- **Fitur/Story:** F-13, US-014
- **Peran:** Pengguna
- **Deskripsi:** Halaman Pengaturan mengelola: API key transkripsi, API key LLM (tersimpan di keyring OS / file `.env` lokal, tidak pernah ditampilkan utuh), bobot Skor Highlight, Jeda Chat, kata reaksi chat, folder kerja & output, jumlah Job berat paralel (default 1), batas durasi audio per Job, dan tombol "Tes koneksi" per API.
- **Kriteria penerimaan:**
  - [ ] Given API key tersimpan, when Pengaturan dibuka, then key tampil termasking (mis. `sk-…a1b2`).
  - [ ] Given Pengguna menekan "Tes koneksi", when key valid, then tampil "Terhubung" dalam ≤ 10 detik; jika tidak valid, tampil pesan error dari penyedia.
  - [ ] Given total bobot ≠ 100%, when menyimpan, then penyimpanan ditolak dengan pesan "Total bobot harus 100%."

### FR-022 Perkiraan pemakaian API
- **Fitur/Story:** F-13, US-014
- **Peran:** Pengguna
- **Deskripsi:** Sebelum Job `transcribe` dimulai untuk Stream Sumber > 30 menit, sistem menampilkan durasi audio yang akan dikirim dan perkiraan jumlah jendela yang dinilai LLM, lalu meminta konfirmasi. Konfirmasi bisa dimatikan di Pengaturan. Sistem tidak menampilkan harga dalam rupiah/dolar karena harga berubah; tersedia tautan ke halaman harga penyedia.
- **Kriteria penerimaan:**
  - [ ] Given Stream Sumber 2 jam 10 menit dan konfirmasi aktif, when transkripsi akan dimulai, then tampil "Audio yang dikirim: 2 jam 10 menit" dan Job baru jalan setelah Pengguna menekan "Lanjutkan".
  - [ ] Given durasi melebihi batas durasi per Job di Pengaturan, when akan dimulai, then Job tidak dijalankan sampai Pengguna menaikkan batas atau memilih rentang waktu tertentu saja.

### FR-023 Pemantauan & kontrol Job
- **Fitur/Story:** F-15, US-015
- **Peran:** Pengguna
- **Deskripsi:** Sistem menampilkan Job aktif dan riwayat beserta progres (%), tahap, waktu mulai, dan log singkat. Pengguna dapat membatalkan Job `queued`/`running` dan mencoba ulang Job `failed`. Coba ulang melanjutkan dari hasil yang sudah tersimpan (checkpoint per potongan/tahap). Saat aplikasi dijalankan ulang, Job `running` yang terputus otomatis ditandai `failed` dengan pesan "Terhenti karena aplikasi ditutup" dan bisa dicoba ulang.
- **Kriteria penerimaan:**
  - [ ] Given Job `transcribe` gagal di potongan 7 dari 20, when Pengguna menekan "Coba lagi", then hanya potongan 7–20 yang dikirim ke API.
  - [ ] Given Job `running`, when Pengguna menekan "Batalkan", then proses berhenti dalam ≤ 10 detik dan Status Job `cancelled`.
  - [ ] Given UI terbuka, when progres Job berubah, then tampilan diperbarui dalam ≤ 3 detik tanpa reload halaman.

### FR-024 Manajemen penyimpanan
- **Fitur/Story:** F-14
- **Peran:** Pengguna
- **Deskripsi:** Daftar Stream Sumber menampilkan ukuran file video sumber, segmen, dan hasil render. Pengguna dapat "Hapus video sumber" (Klip yang sudah dirender tetap ada; Klip yang belum dirender tidak bisa dirender/diedit lagi) atau "Hapus Stream Sumber" (menghapus semua data & file terkait kecuali file render di folder output).
- **Kriteria penerimaan:**
  - [ ] Given Stream Sumber dengan 3 Klip `approved` belum dirender, when Pengguna memilih "Hapus video sumber", then tampil peringatan "3 klip belum dirender dan tidak bisa dirender setelah ini."
  - [ ] Given penghapusan dikonfirmasi, when selesai, then ukuran yang dibebaskan ditampilkan dan file benar-benar hilang dari folder kerja.

### Unggah manual & caption

### FR-025 Mode Unggah & Paket Unggah manual
- **Fitur/Story:** F-16, US-017, US-018
- **Peran:** Pengguna
- **Deskripsi:** Di dialog unggah, setiap Platform Tujuan punya pilihan Mode Unggah `manual` atau `auto`. Default `manual`. `auto` hanya bisa dipilih jika Akun Unggah platform itu terhubung. Memilih `manual` lalu "Siapkan" membuat Unggahan (`mode = manual`, `pending`) dan menampilkan Paket Unggah per platform: tombol "Unduh MP4", "Unduh .srt", judul dan caption + hashtag dengan tombol "Salin", tombol "Buka halaman upload {Platform}" (membuka situs upload resmi platform di tab baru), dan "Buka folder" (membuka folder output di file explorer).
- **Kriteria penerimaan:**
  - [ ] Given Klip `rendered` dan tidak ada Akun Unggah terhubung, when dialog unggah dibuka, then semua platform default `manual` dan opsi `auto` nonaktif dengan tautan "Hubungkan akun".
  - [ ] Given Pengguna memilih TikTok & Instagram mode `manual` dan menekan "Siapkan", when selesai, then 2 Unggahan `manual`/`pending` dibuat dan Paket Unggah keduanya tampil dalam ≤ 2 detik.
  - [ ] Given Pengguna menekan "Salin" pada caption TikTok, when berhasil, then teks caption + hashtag tersalin ke clipboard dan tampil "Tersalin".
  - [ ] Given Klip berstatus selain `rendered`, when Pengguna membuka dialog unggah, then dialog tidak bisa dibuka dengan pesan "Render klip dulu." (BR-007).

### FR-026 Tandai sudah diposting (manual)
- **Fitur/Story:** F-16, US-018
- **Peran:** Pengguna
- **Deskripsi:** Pada Unggahan `manual`/`pending`, Pengguna menekan "Tandai sudah diposting" dan boleh mengisi URL postingan. Status menjadi `uploaded`. Pengguna juga bisa "Batalkan" Unggahan manual `pending` (record dihapus).
- **Kriteria penerimaan:**
  - [ ] Given Unggahan manual TikTok `pending`, when Pengguna mengisi URL `https://www.tiktok.com/@akun/video/123` dan menekan "Tandai sudah diposting", then status `uploaded`, URL tersimpan, dan badge platform TikTok tampil di kartu Klip P-04.
  - [ ] Given URL yang domainnya tidak cocok dengan platform (mis. URL YouTube pada Unggahan TikTok), when disimpan, then ditolak dengan pesan "URL tidak sesuai platform TikTok."
  - [ ] Given URL dikosongkan, when ditandai, then status tetap `uploaded` tanpa URL.

### FR-027 Draf caption per platform
- **Fitur/Story:** F-17, US-019
- **Peran:** Pengguna
- **Deskripsi:** Saat dialog unggah dibuka pertama kali untuk sebuah Klip, sistem meminta LLM membuat draf per Platform Tujuan yang dicentang dari transkrip Klip, judul Klip, Kanal, dan kategori: judul (YouTube), caption, dan 3–8 hashtag. Draf mengikuti gaya platform dan bahasa Bahasa Tampil Klip. Draf di-cache di Klip dan bisa dibuat ulang ("Buat ulang") atau diedit. Template tetap per platform di Pengaturan (mis. selalu tambahkan "Klip dari {kanal}") ditambahkan di akhir caption.
- **Kriteria penerimaan:**
  - [ ] Given Klip berbahasa Indonesia dan platform TikTok & YouTube dicentang, when dialog dibuka, then dalam ≤ 15 detik tampil draf caption TikTok dan judul + deskripsi YouTube berbahasa Indonesia, masing-masing dalam batas panjang platform.
  - [ ] Given LLM gagal atau API key kosong, when dialog dibuka, then draf terisi template default `"{judul Klip} | Klip dari {Kanal}"` dengan pesan "Draf otomatis tidak tersedia."
  - [ ] Given Pengguna mengedit caption lalu menutup dialog, when dialog dibuka lagi, then hasil edit tetap ada (tidak ditimpa draf baru).

## 2. Aturan Bisnis
| ID | Aturan | Berlaku di |
|---|---|---|
| BR-001 | Skor Highlight = 100 × (w_audio × Sinyal Audio + w_chat × Sinyal Chat + w_llm × Sinyal LLM/100). Bobot default w_audio = 0,30, w_chat = 0,20, w_llm = 0,50; total wajib 1,00 | FR-012, FR-021 |
| BR-002 | Jika Sinyal Chat tidak tersedia, w_chat dibagi ke w_audio dan w_llm secara proporsional. Jika Sinyal LLM null untuk satu jendela, skor jendela memakai Sinyal yang tersedia saja dan diberi tanda "skor parsial" | FR-010, FR-011, FR-012 |
| BR-003 | Pra-seleksi LLM: hanya jendela 60 detik (geser 30 detik) dengan (0,6 × Audio + 0,4 × Chat) di persentil ≥ 80, ditambah sampel acak 5% jendela lain, maks. 120 jendela per jam stream, yang dikirim ke LLM | FR-011 |
| BR-004 | Durasi Klip 15–90 detik. Rentang di luar batas dikoreksi otomatis untuk `origin = auto` atau wajib di-trim Pengguna sebelum `approved` untuk `origin = live_marker`/`manual` | FR-004, FR-011, FR-012, FR-014, FR-015 |
| BR-005 | Kandidat Klip `origin = auto` dalam satu Stream Sumber tidak boleh tumpang tindih > 5 detik; jika bentrok, yang skornya lebih tinggi dipertahankan | FR-012 |
| BR-006 | Jumlah Kandidat Klip `origin = auto` = min(20, maks(3, ceil(durasi_jam × 5))), hanya jendela dengan Skor Highlight ≥ 40 | FR-012 |
| BR-007 | Hanya Klip `approved` (atau `render_failed`) yang boleh dirender; hanya Klip `rendered` yang boleh diunggah, baik manual maupun otomatis | FR-018, FR-020, FR-025 |
| BR-008 | Subtitle terjemahan (`subtitle_language = id` pada stream non-Indonesia) selalu mode `sentence` memakai timestamp baris asli; mode `word_highlight` hanya untuk bahasa asli | FR-016, FR-017 |
| BR-009 | Satu Klip hanya boleh punya satu Unggahan aktif/berhasil (`pending`, `uploading`, `uploaded`) per Platform Tujuan, apa pun Mode Unggah-nya; unggah ulang hanya jika Unggahan sebelumnya `failed` atau Unggahan manual `pending` dibatalkan | FR-020, FR-025, FR-026 |
| BR-013 | Mode Unggah `auto` hanya boleh dipilih untuk Platform Tujuan yang punya Akun Unggah terhubung dan Klip memenuhi batas platform (durasi, ukuran, format); mode `manual` selalu tersedia | FR-020, FR-025 |
| BR-014 | Jika Klip yang sudah punya Unggahan `uploaded` diedit dan dirender ulang, Unggahan lama tetap tercatat (riwayat) dan tidak diperbarui otomatis; memposting versi baru membutuhkan Unggahan baru setelah Unggahan lama dihapus dari riwayat oleh Pengguna | FR-015, FR-020, FR-025 |
| BR-010 | Waktu di semua entitas disimpan dalam milidetik relatif terhadap awal Stream Sumber (`*_ms`), sedangkan waktu kejadian (`created_at`) disimpan dalam UTC | FR-004, FR-005, FR-012 |
| BR-011 | Edit subtitle disimpan di level Klip (`clips.subtitle_overrides`) dan tidak mengubah Kata Transkrip asli | FR-015 |
| BR-012 | Aplikasi hanya mendengarkan koneksi di alamat loopback (`127.0.0.1` dan `::1`, diakses sebagai `127.0.0.1` atau `localhost`); tidak boleh diakses dari perangkat lain di jaringan | NFR-005 |

## 3. Validasi Data
| Field | Aturan | Pesan error |
|---|---|---|
| URL Impor | Wajib; domain `youtube.com`, `youtu.be`, atau `kick.com`; dapat di-resolve yt-dlp | "URL tidak dikenali. Gunakan link VOD YouTube atau Kick." |
| File lokal | Ekstensi mp4/mkv/mov/webm; ada trek video dan audio; ≤ 20 GB | "Format tidak didukung atau file tidak memiliki audio." |
| Durasi "Klip N detik terakhir" | Bilangan bulat 15–90 | "Pilih durasi antara 15 dan 90 detik." |
| Rentang Klip | `start_ms` < `end_ms`; durasi 15–90 detik saat disetujui; dalam durasi Stream Sumber | "Durasi klip harus 15–90 detik." |
| Region Cam | x, y, lebar, tinggi di 0–1; lebar & tinggi ≥ 0,05; x+lebar ≤ 1; y+tinggi ≤ 1 | "Area kamera di luar frame atau terlalu kecil." |
| Judul unggahan (YouTube) | Wajib untuk platform `youtube`; 1–100 karakter; tanpa karakter `<` `>` | "Judul wajib 1–100 karakter." |
| Caption/deskripsi unggahan | Panjang maksimum sesuai batas platform di konfigurasi adapter (07-integrasi.md); default batas aman 2.000 karakter jika belum dikonfirmasi | "Caption melebihi batas {Platform} ({n} karakter)." |
| Hashtag | 0–30 item; tiap item diawali `#`, tanpa spasi, ≤ 50 karakter | "Hashtag tidak valid: {item}" |
| URL postingan manual | Opsional; jika diisi harus `https://` dan domain sesuai platform: `youtube.com`/`youtu.be`, `tiktok.com`, `instagram.com`, `facebook.com`/`fb.watch` | "URL tidak sesuai platform {Platform}." |
| Mode Unggah | `manual` atau `auto`; `auto` hanya jika BR-013 terpenuhi | "Hubungkan akun {Platform} dulu untuk unggah otomatis." |
| Bobot skor | Masing-masing 0–1; total = 1,00 (toleransi 0,001) | "Total bobot harus 100%." |
| Jeda Chat | 0–30 detik | "Jeda chat harus 0–30 detik." |
| API key | Wajib sebelum Job terkait; tidak kosong; lolos "Tes koneksi" | "API key belum diisi atau tidak valid." |
| Posisi subtitle | 5–95 (% dari atas) | "Posisi subtitle harus 5–95%." |

## 4. Kebutuhan Non-Fungsional
| ID | Kategori | Kebutuhan terukur | Cara verifikasi |
|---|---|---|---|
| NFR-001 | Performa | Untuk VOD 3 jam yang sudah terunduh, tahap lokal (ekstrak audio, deteksi layout, Sinyal Audio/Chat) selesai ≤ 15 menit di laptop CPU 4 core/16 GB RAM tanpa GPU | Ukur dengan data uji 3 jam (09-testing.md) |
| NFR-002 | Performa | Render Klip 60 detik selesai ≤ 2 menit di spesifikasi NFR-001 | Ukur 10 render, ambil median |
| NFR-003 | Performa | Halaman daftar Klip (≤ 200 Klip) dan pratinjau frame tampil ≤ 2 detik | Uji manual dengan DevTools |
| NFR-004 | Ketahanan | Aplikasi ditutup paksa saat Job berjalan tidak merusak database; Job dapat dicoba ulang dari checkpoint terakhir | Uji kill proses di tengah `transcribe` dan `render` |
| NFR-005 | Keamanan | Server hanya bind ke alamat loopback (`127.0.0.1`, `::1`); API key & token OAuth tidak pernah muncul di log, respons API UI, atau repo | Cek `netstat`; grep log & respons untuk pola key |
| NFR-006 | Keamanan | Token OAuth semua platform disimpan di keyring OS atau file terenkripsi; tiap platform hanya meminta scope minimum untuk memposting dan membaca identitas akun sendiri (daftar scope di 07-integrasi.md) | Review kode & layar persetujuan tiap platform |
| NFR-007 | Kompatibilitas | UI berjalan di Chrome/Edge versi stabil terbaru dan Firefox terbaru, layar ≥ 1280×720; backend di Windows 10/11 dan macOS 13+ dengan Python 3.11+ dan FFmpeg 6+ | Uji manual di tiap OS/browser |
| NFR-008 | Ketersediaan | Kegagalan satu penyedia API tidak menghentikan tahap lain: deteksi layout & Sinyal Audio tetap selesai walau transkripsi gagal | Uji dengan API key salah |
| NFR-009 | Aksesibilitas | Semua aksi utama (Setujui, Tolak, Tandai, Putar/Jeda, trim) punya pintasan keyboard; kontras teks UI memenuhi WCAG AA | Uji keyboard-only & cek kontras |
| NFR-010 | Pencadangan | Database SQLite dicadangkan otomatis harian (simpan 7 salinan terakhir) di folder kerja; tidak mencadangkan file video | Cek folder backup setelah 2 hari pemakaian |
| NFR-011 | Penyimpanan | Segmen live sementara dihapus otomatis setelah digabung dan diverifikasi | Cek folder segmen setelah FR-003 selesai |
| NFR-012 | Biaya | Untuk stream 1 jam, LLM menerima ≤ 120 jendela (BR-003) | Hitung panggilan LLM di log Job |

## 5. Matriks Penelusuran
| Fitur | User Story | FR |
|---|---|---|
| F-01 Impor VOD dari URL | US-001 | FR-001 |
| F-02 Impor file lokal | US-002 | FR-002 |
| F-03 Rekam & pantau live | US-003, US-004 | FR-003, FR-004 |
| F-04 Transkripsi otomatis | US-005 | FR-005 |
| F-05 Deteksi posisi cam & Preset Layout | US-006, US-007 | FR-006, FR-007, FR-008 |
| F-06 Deteksi Kandidat Klip | US-008 | FR-009, FR-010, FR-011, FR-012 |
| F-07 Analisis live bertahap | US-003 | FR-013 |
| F-08 Review & edit klip | US-008, US-009 | FR-014, FR-015 |
| F-09 Subtitle otomatis | US-010, US-011 | FR-016, FR-017 |
| F-10 Render klip | US-012 | FR-018 |
| F-11 Unggah otomatis YouTube | US-013 | FR-019, FR-020 |
| F-12 Unggah otomatis TikTok, Instagram, Facebook | US-016 | FR-019, FR-020 |
| F-16 Mode Unggah & unggah manual | US-017, US-018 | FR-025, FR-026 |
| F-17 Caption per platform | US-019 | FR-027 |
| F-13 Pengaturan & perkiraan pemakaian | US-014 | FR-021, FR-022 |
| F-14 Manajemen penyimpanan | — | FR-024 |
| F-15 Pemantauan Job | US-015 | FR-023 |

## Keputusan implementasi (disetujui pemilik 2026-11-21)
Keputusan yang diambil saat implementasi karena spesifikasi belum merinci; nomor K-xx sama dengan riwayat di `docs/CATATAN-SESI.md`.

- **K-30** (angka dikalibrasi ulang di T-062) Sinyal Audio: loudness = RMS dBFS per detik dari PCM mono 8 kHz (FFmpeg pipe, lantai −100 dB untuk hening digital; dipilih alih-alih `ebur128`/`astats` karena lebih sederhana & bisa dibatalkan). Satuan = simpangan baku loudness seluruh stream (min. 1 dB). Pemetaan kenaikan terhadap rata-rata 60 dtk sebelumnya: ≤ 1σ → 0, 2σ → 0,8, ≥ 2,25σ → 1 (tanpa ambang 1σ, fluktuasi wajar audio tenang sudah ±0,4 sehingga melanggar "jendela tenang < 0,3"). Sinyal jendela = maksimum per detik. Video tanpa audio → array kosong (sinyal 0) _(kode: `highlight/audio_signal.py`)_
- **K-31** (angka dikalibrasi ulang di T-062) Sinyal Chat: ember 10 dtk setelah digeser mundur `chat_delay_ms` (offset < 0 diabaikan); bobot reaksi 1,5× dihitung ulang dari teks dengan `chat_reaction_words` saat skor (kolom `is_reaction` hanya hasil impor); rasio terhadap median ember ±150 dtk dengan lantai 1 pesan; sinyal = (rasio − 1)/4 dibatasi 0–1 (5× median = 1); sinyal jendela = ember tertinggi yang beririsan. BR-002 (`highlight/scoring.py`): tanpa chat → `w_chat` dibagi proporsional ke audio & LLM; LLM null → bobot audio+chat dinormalkan ulang dan `partial = true`; skor dibulatkan ke integer 0–100. Pembaca Pengaturan lewat Connection: `app_settings.value` _(kode: `highlight/chat_signal.py`, `highlight/scoring.py`)_
- **K-32** Pra-seleksi BR-003 (`highlight/preselect.py`): jendela terakhir dipotong di akhir rentang, jendela < 15 dtk tidak dibuat (kecuali stream sangat pendek: 1 jendela); tanpa chat skor pra-seleksi = Audio saja; persentil 80 inklusif (nilai sama → ikut); sampel acak 5% = ceil(5% × sisa) dengan seed id Stream Sumber (hasil sama saat rescore); batas = ceil(jam × 120), yang dipertahankan: skor tertinggi lalu sampel acak; `store` menghapus jendela di luar set baru dan tidak menimpa kolom `llm_*`. `build_windows(start, end, …)` menerima rentang transkripsi (pemanggilnya T-039). Dependensi dev baru: `hypothesis` _(kode: `highlight/preselect.py`)_
- **K-34** `score_highlights`: rentang jendela = `checkpoint.range` Job `transcribe` seluruh stream terakhir yang sukses (FR-022); bila `highlight_windows` sudah ada (rescore/coba ulang) sinyal & pra-seleksi tersimpan dipakai ulang tanpa dekode audio — perubahan Jeda Chat/kata reaksi baru berlaku pada stream yang dianalisis ulang dari awal. LLM hanya untuk jendela terpilih yang belum `done` (`invalid`/`failed` dicoba lagi saat rescore). Konteks transkrip = jendela ±15 dtk (≈ 90 dtk), waktu relatif awal jendela (bisa negatif). Koreksi BR-004: saran LLM dijepit ke jendela, < 15 dtk diperpanjang simetris lalu digeser masuk ke jendela, > 90 dtk dipendekkan di tengah. BR-005 juga menghindari Klip `auto` yang sudah direview (approved/rejected/rendering/rendered/render_failed); kuota BR-006 hanya untuk kandidat baru. Judul tanpa LLM: `"{Kanal atau judul stream} - mm:ss"` (h:mm:ss bila ≥ 1 jam); gaya subtitle = `default_subtitle_style`. Rescore: stream `ready` → `processing` → `ready`. `FakeJudge` menyarankan seluruh jendela _(kode: `highlight/candidates.py`, `worker/handlers/score_highlights.py`, `streams.rescore`)_

## Asumsi & Pertanyaan Terbuka
- [ASUMSI] Bobot skor default (30/20/50), ambang skor 40, dan rumus jumlah kandidat (BR-006) adalah titik awal; dikalibrasi setelah uji dengan 3–5 stream nyata.
- [ASUMSI] Jeda Chat default 8 detik; bisa berbeda antara YouTube dan Kick.
- [ASUMSI] Kualitas unduhan maksimal 1080p cukup untuk output 1080×1920 (area facecam kecil akan di-upscale; kualitasnya bisa turun).
- [ASUMSI] Deteksi pembicara aktif untuk `podcast` memetakan label diarization ke posisi wajah berdasarkan kecocokan waktu bicara dengan gerak mulut/kemunculan wajah; akurasinya perlu divalidasi saat implementasi.
- [ASUMSI] Spesifikasi acuan performa: laptop CPU 4 core, RAM 16 GB, tanpa GPU.
- [TANYA] Apakah kata reaksi chat bawaan (bahasa gaul Indonesia + emote Kick/YouTube) perlu disesuaikan per Kanal? (Pengguna)
- [TERJAWAB] Dukungan Bahasa Indonesia & diarization penyedia transkripsi: lihat 07-integrasi.md INT-04 (batas ukuran per request dicek saat implementasi T-028/T-029).
- [TERJAWAB] Ketentuan unggah YouTube via API dari project belum diverifikasi (dikunci private, kuota 100 `videos.insert`/hari): 07-integrasi.md INT-07.

## Riwayat Perubahan
| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.3 | 2026-11-21 | Keputusan implementasi disetujui pemilik (K-30, K-31, K-32, K-34): pemetaan Sinyal Audio/Chat ke 0–1, detail pra-seleksi BR-003, koreksi BR-004/BR-005 dan rescore |
| 1.0 | 2026-11-20 | Draf awal |
| 1.2 | 2026-11-20 | Hasil CEK #3: redirect OAuth diseragamkan ke `http://localhost:{port}`; BR-012 & NFR-005 mencakup loopback IPv6 (`::1`) karena `localhost` bisa resolve ke IPv6. Hasil CEK #11: pertanyaan yang sudah dijawab 07-integrasi.md ditandai terjawab |
| 1.1 | 2026-11-20 | Menyesuaikan perubahan unggah multi-platform & Mode Unggah (01-prd.md v1.1): FR-019 & FR-020 jadi multi-platform; tambah FR-025 Paket Unggah manual, FR-026 Tandai sudah diposting, FR-027 draf caption per platform; BR-007 & BR-009 diperbarui, tambah BR-013 & BR-014; validasi caption/hashtag/URL; NFR-006; Matriks Penelusuran |
