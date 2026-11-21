# Respons penyedia untuk tes kontrak

Setiap file dibuat dari format respons di dokumentasi resmi penyedia,
bukan dari panggilan API berbayar, dan bentuknya belum bisa dipastikan sebelum
adapternya ditulis. Rencananya ditambahkan bersama task adapternya. Nama file mengikuti
pola `{penyedia}_{kasus}.json`, misalnya `deepgram_success.json`, `deepgram_401.json`,
`deepgram_429.json`, `deepgram_5xx.json`.

| Penyedia | Task |
|---|---|
| Deepgram | T-028 (ada) |
| AssemblyAI | T-029 (ada) |
| Anthropic (HighlightJudge, Translator, CaptionWriter) | T-038, T-044, T-056 |
| YouTube, TikTok, Instagram, Facebook | v1.1 |

## Deepgram (T-028)

Dari dokumentasi resmi Deepgram (dicek 2026-11-21: referensi `POST /v1/listen`, halaman
errors, language detection, diarization, utterances, `GET /v1/projects`). Isi transkrip,
ID, dan hash fiktif.

| File | Isi |
|---|---|
| `deepgram_success.json` | 200: `results.channels[0].detected_language = "id"`, kata dengan `speaker`/`punctuated_word`, `results.utterances` |
| `deepgram_400.json` | 400 audio rusak (`err_code` "Bad Request") |
| `deepgram_401.json` | 401 `INVALID_AUTH` |
| `deepgram_429.json` | 429 `TOO_MANY_REQUESTS` |
| `deepgram_5xx.json` | 5xx; bentuk body 5xx STT **tidak didokumentasikan**, jadi dipakai format lama `err_code`/`err_msg` (adapter tidak bergantung pada isinya) |
| `deepgram_projects.json` | 200 `GET /v1/projects` (tes koneksi) |

## AssemblyAI (T-029)

Dari dokumentasi resmi AssemblyAI (dicek 2026-11-21: referensi upload, submit/get/delete/list
transcript, pemilihan model, deteksi bahasa, label pembicara, batas laju). Isi fiktif.

| File | Isi |
|---|---|
| `assemblyai_upload.json` | 200 `POST /v2/upload` → `upload_url` |
| `assemblyai_queued.json` | 200 `POST /v2/transcript` / polling: `status = queued` |
| `assemblyai_completed.json` | `status = completed`, `language_code = id`, `words` & `utterances` (ms, pembicara `A`/`B`) |
| `assemblyai_error_status.json` | `status = error` dengan alasan di `error` |
| `assemblyai_401.json` | 401 `{"error": "Authentication error, API token missing/invalid"}` |
| `assemblyai_429.json` | 429 (body tidak dirinci di dokumentasi; dipakai `{"error": ...}`) |
| `assemblyai_5xx.json` | 5xx (body tidak dirinci; dipakai `{"error": ...}`) |
| `assemblyai_list.json` | 200 `GET /v2/transcript?limit=1` (tes koneksi; bentuk akun tanpa transkrip diasumsikan daftar kosong) |
