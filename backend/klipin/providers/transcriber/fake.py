"""`FakeTranscriber` (KLIPIN_PROVIDERS=fake): transkrip deterministik tanpa jaringan & biaya.

Naskah tetap: kalimat ke-k dimulai pada detik 6k **relatif awal Stream Sumber**, 4–6 kata
berjarak 1 detik (panjang 0,8 detik), pembicara lokal bergantian "0"/"1". Karena posisinya absolut, dua
potongan yang tumpang tindih mengembalikan kata yang sama di zona tumpang tindih — persis
kasus yang harus dijahit handler (TC-011). Rentang hening (`silent_ranges`) tidak berisi kata.
Kegagalan bisa diskenariokan per indeks potongan (TC-012, TC-013).
"""

from collections.abc import Iterable

from klipin.providers.transcriber.base import (
    AudioChunk,
    Transcriber,
    TranscriberAuthError,
    TranscriptionResult,
    Utterance,
    Word,
)

SENTENCES = (
    "halo semuanya selamat datang lagi",
    "hari ini kita main sampai pagi",
    "eh itu apa di belakang",
    "gila kaget banget aku tadi",
    "oke lanjut ke bagian berikutnya",
    "jangan lupa follow dan subscribe",
)
SENTENCE_EVERY_MS = 6000
WORD_EVERY_MS = 1000
WORD_LEN_MS = 800
LOW_CONFIDENCE_EVERY = 7  # setiap kata ke-7 ber-confidence rendah (untuk sorotan di P-05)


class FakeTranscriber(Transcriber):
    name = "fake"

    def __init__(self, api_key: str = "fake-key", *, language: str = "id",
                 silent_ranges: Iterable[tuple[int, int]] = (),
                 failures: dict[int, list[Exception]] | None = None) -> None:
        self.api_key = api_key
        self.language = language
        self.silent_ranges = list(silent_ranges)
        self.failures = {k: list(v) for k, v in (failures or {}).items()}
        self.calls: list[AudioChunk] = []  # potongan yang benar-benar "dikirim"

    def _silent(self, start_ms: int, end_ms: int) -> bool:
        return any(start_ms < e and end_ms > s for s, e in self.silent_ranges)

    def transcribe(self, chunk: AudioChunk) -> TranscriptionResult:
        self.calls.append(chunk)
        if self.api_key.startswith("invalid"):  # sama dengan tes koneksi palsu (T-012)
            raise TranscriberAuthError("401 invalid api key")
        if pending := self.failures.get(chunk.index):
            raise pending.pop(0)

        utterances = []
        first = max(0, chunk.start_ms // SENTENCE_EVERY_MS - 1)
        for k in range(first, chunk.end_ms // SENTENCE_EVERY_MS + 1):
            words = []
            for i, text in enumerate(SENTENCES[k % len(SENTENCES)].split()):
                start = k * SENTENCE_EVERY_MS + i * WORD_EVERY_MS
                end = start + WORD_LEN_MS
                if start < chunk.start_ms or end > chunk.end_ms or self._silent(start, end):
                    continue
                n = k * 10 + i
                words.append(Word(
                    start_ms=start - chunk.start_ms, end_ms=end - chunk.start_ms, word=text,
                    confidence=0.55 if n % LOW_CONFIDENCE_EVERY == 0 else 0.95,
                    speaker=str(k % 2)))
            if words:
                utterances.append(Utterance(
                    start_ms=words[0].start_ms, end_ms=words[-1].end_ms,
                    text=" ".join(w.word for w in words), speaker=words[0].speaker, words=words))
        return TranscriptionResult(language=chunk.language or self.language,
                                   utterances=utterances)
