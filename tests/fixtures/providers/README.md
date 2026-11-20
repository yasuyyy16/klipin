# Respons penyedia untuk tes kontrak

Belum ada isinya. Setiap file dibuat dari format respons di dokumentasi resmi penyedia,
bukan dari panggilan API berbayar, dan bentuknya belum bisa dipastikan sebelum
adapternya ditulis. Rencananya ditambahkan bersama task adapternya. Nama file mengikuti
pola `{penyedia}_{kasus}.json`, misalnya `deepgram_success.json`, `deepgram_401.json`,
`deepgram_429.json`, `deepgram_5xx.json`.

| Penyedia | Task |
|---|---|
| Deepgram | T-028 |
| AssemblyAI | T-029 |
| Anthropic (HighlightJudge, Translator, CaptionWriter) | T-038, T-044, T-056 |
| YouTube, TikTok, Instagram, Facebook | v1.1 |
