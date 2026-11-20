# Fixture uji

Data uji untuk 09-testing.md §5. Semua file di folder ini dibuat sendiri oleh
`generate.py` dari generator bawaan FFmpeg (`testsrc2`, `anullsrc`, `anoisesrc`) dan
Python. Tidak ada materi pihak ketiga, jadi bebas dipakai (milik proyek Klipin).

Membuat ulang (butuh FFmpeg di PATH):

```
uv run python tests/fixtures/generate.py
```

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

## Belum ada

| File | Kenapa belum | Dipakai di |
|---|---|---|
| `gaming_facecam_30s.mp4` + `gaming_facecam_30s.regions.json` (ground truth Region Cam) | Butuh rekaman wajah sungguhan; MediaPipe tidak mendeteksi wajah sintetis. Menunggu keputusan sumber wajah | TC-015, TC-018 |
| `podcast_two_faces_30s.mp4` | Sama: butuh dua wajah sungguhan | TC-019 |
| `irl_moving_face_30s.mp4` | Sama: butuh satu wajah bergerak | preset `irl` |
| `providers/*.json` | Lihat `providers/README.md` | tes kontrak adapter |
