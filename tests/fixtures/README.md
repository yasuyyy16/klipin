# Fixture uji

Data uji untuk 09-testing.md §5, dibuat oleh `generate.py`. Fixture sintetis berasal dari
generator bawaan FFmpeg (`testsrc2`, `anullsrc`, `anoisesrc`) dan Python. Fixture berwajah
memakai potongan dua video **domain publik** dari Wikimedia Commons (lihat tabel sumber).

Membuat ulang (butuh FFmpeg di PATH):

```
uv run python tests/fixtures/generate.py
uv run python tests/fixtures/generate.py --only-faces --faces SASHA.webm RIMPAC.webm
```

Video sumber wajah tidak disimpan di repo. Unduh file aslinya dari halaman Commons di
tabel sumber; `generate.py` menolak file yang SHA1-nya berbeda.

| File | Isi | Sumber & lisensi | Dipakai di |
|---|---|---|---|
| `no_face_30s.mp4` | 30 dtk, 960×540, 30 fps, pola uji bergerak (pengganti layar game, tanpa wajah) + nada 330 Hz (AAC) | Dibuat sendiri, `testsrc2` + `sine` | TC-016 |
| `no_audio_10s.mp4` | 10 dtk, pola uji yang sama, **tanpa** trek audio | Dibuat sendiri | TC-006 |
| `corrupt.mp4` | 30% awal MP4 5 dtk; atom `moov` hilang sehingga FFprobe gagal ("moov atom not found") | Dibuat sendiri | TC-039 |
| `audio_25min_scream_at_10.flac` | 25:00 mono 16 kHz; hening (sekitar -91 dB), lalu semburan pink noise keras 3 dtk di 10:00–10:03 (sekitar -15 dB) | Dibuat sendiri, `anullsrc` + `anoisesrc` (seed 7) | TC-011, TC-020 |
| `live_chat_spike.jsonl` | Chat replay format yt-dlp `live_chat` (satu `replayChatItemAction` per baris), 20 menit; 2 pesan per 10 dtk, jendela 600–610 dtk berisi 10 pesan kata reaksi (5× median); plus 1 super chat (`liveChatPaidMessageRenderer`) dan 1 membership | Dibuat sendiri (seed 1234), nama penonton fiktif | TC-021, T-023 |

Catatan: lantai "audio tenang" berupa hening digital, bukan nada pelan, karena nada pelan
membuat FLAC lebih dari 6 MB. Bagi Sinyal Audio (loudness per detik lalu z-score) bentuknya
setara: rendah dan rata, lalu satu lonjakan.

## Respons yt-dlp tersimpan (`ytdlp/`)

Info dict `YoutubeDL.extract_info(..., download=False)` yang dipangkas ke field yang dibaca
`media/ytdlp.py`, ditulis tangan mengikuti bentuk keluaran yt-dlp 2026.10.26 (nama field dan
`extractor_key` dicek di kode extractor). ID, judul, dan nama kanal fiktif. Dipakai di T-021.

| File | Kasus |
|---|---|
| `youtube_vod_chat.json` | VOD YouTube bekas live, subtitle `live_chat` ada, format 1080p + audio dengan `filesize`/`filesize_approx` |
| `youtube_live.json` | YouTube sedang live (`live_status = is_live`), durasi belum ada |
| `kick_vod.json` | VOD Kick (`KickVOD`), satu format HLS tanpa ukuran (perkiraan dari `tbr` × durasi) |

Uji unduh memakai yt-dlp sungguhan terhadap server HTTP lokal yang menyajikan
`no_audio_10s.mp4` (dengan dukungan `Range` untuk uji lanjutan).

## Fixture berwajah

Semua 30 dtk, 960×540, 30 fps, H.264 + AAC. Hanya potongan wawancara menghadap kamera yang
dipakai (b-roll dibuang), disambung lalu diulang sampai 30 detik.

| File | Isi | Dipakai di |
|---|---|---|
| `gaming_facecam_30s.mp4` | Pola uji (pengganti layar game) + facecam 320×240 berisi wajah sumber A di pojok kanan bawah, posisi tetap; audio = suara sumber A | TC-015, TC-018 |
| `gaming_facecam_30s.regions.json` | Ground truth Region Cam (format `cam_regions`, ternormalisasi 0–1): `cam` x 0,65, y 0,525926, w 0,333333, h 0,444444; saran preset `gaming` | TC-015 |
| `podcast_two_faces_30s.mp4` | Panel kiri sumber A, panel kanan sumber B; yang terdengar bergantian tiap 5 dtk (kiri dulu) | TC-019 |
| `podcast_two_faces_30s.regions.json` | `face_a` (panel kiri), `face_b` (panel kanan), jadwal pembicara `S1`/`S2` per 5 dtk | TC-019 |
| `irl_moving_face_30s.mp4` | Wajah sumber B bergerak pelan kiri-kanan dan atas-bawah (jendela crop bergeser, periode 12 dtk dan 9 dtk) | preset `irl` |

Sumber (keduanya karya pemerintah AS, domain publik):

| | Judul di Wikimedia Commons | Pembuat | SHA1 | Potongan dipakai (dtk) |
|---|---|---|---|---|
| A | [Faces of Keen Sword - Tech Sgt Sasha Marceaux (1027106).webm](https://commons.wikimedia.org/wiki/File:Faces_of_Keen_Sword_-_Tech_Sgt_Sasha_Marceaux_(1027106).webm) | U.S. Army 314PAOC, Spc. Wesley Richardson | `9c022062c6565af5681c6d5a1343ef2a57a0e83a` | 5,6–10,3; 14,6–19,8; 24,9–30,8 |
| B | [Faces of RIMPAC Philippines.webm](https://commons.wikimedia.org/wiki/File:Faces_of_RIMPAC_Philippines.webm) | U.S. Navy, PO2 Kory Alsberry | `bb6852df5f6f3a7aabe59c5171836117f3a06201` | 11,2–19,2; 25,8–29,2; 34,7–42,4 |

Video ini menampilkan orang sungguhan. Pakai hanya sebagai data uji Klipin, jangan
diunggah ulang sebagai konten.

Pemeriksaan: lembar kontak satu frame per detik menunjukkan wajah ada di setiap detik
ketiga video. Deteksi wajah (MediaPipe BlazeFace + YuNet, model di `backend/klipin/layout/models/`)
menemukan wajah di semua fixture berwajah dan tidak menemukan apa pun di `no_face_30s.mp4`;
Region Cam `gaming` hasil deteksi ber-IoU ±0,99 terhadap ground truth (T-031, TC-015).

## Belum ada

| File | Kenapa belum | Dipakai di |
|---|---|---|
| `providers/*.json` | Lihat `providers/README.md` | tes kontrak adapter |
