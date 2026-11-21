"""Antarmuka `Transcriber` (ADR-003, INT-04) dan bentuk hasil yang sudah dinormalkan.

Waktu di hasil **relatif terhadap awal potongan audio**; handler `transcribe` (T-027) menambah
`chunk.start_ms`, menjahit zona tumpang tindih, dan menormalkan label pembicara ke S1/S2/….
Retry (2/4/8 detik) juga di handler; adapter cukup melempar `TranscriberTransientError`.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

MSG_API_KEY = "API key transkripsi belum diisi atau tidak valid. Buka Pengaturan."
MSG_BAD_AUDIO = "Penyedia transkripsi menolak potongan audio (audio rusak atau format salah)."
MSG_TRANSIENT = "Penyedia transkripsi sedang sibuk atau tidak menjawab."


@dataclass(frozen=True)
class AudioChunk:
    """Satu potongan audio (`transcription_chunks`); `language=None` → minta deteksi bahasa."""

    path: Path
    index: int
    start_ms: int
    end_ms: int
    language: str | None = None


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    word: str
    confidence: float | None = None
    speaker: str | None = None  # label lokal penyedia, belum dinormalkan


@dataclass(frozen=True)
class Utterance:
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None
    words: list[Word] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptionResult:
    language: str | None
    utterances: list[Utterance]


class TranscriberError(Exception):
    """Gagal permanen; `str(e)` adalah pesan Bahasa Indonesia untuk Pengguna."""


class TranscriberAuthError(TranscriberError):
    """API key kosong / 401 / 403: Job gagal segera, tanpa retry."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(MSG_API_KEY)
        self.detail = detail


class TranscriberBadAudioError(TranscriberError):
    """400: potongan ditandai `failed`, Job gagal."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(MSG_BAD_AUDIO)
        self.detail = detail


class TranscriberTransientError(TranscriberError):
    """429 / 5xx / timeout: boleh dicoba ulang (maks. 3×, backoff 2/4/8 detik)."""

    def __init__(self, detail: str = "", status: int | None = None) -> None:
        super().__init__(MSG_TRANSIENT)
        self.detail = detail
        self.status = status


class Transcriber(ABC):
    name: str

    @abstractmethod
    def transcribe(self, chunk: AudioChunk, *,
                   should_cancel: Callable[[], bool] | None = None) -> TranscriptionResult:
        """Kirim satu potongan audio; kata + timestamp + pembicara + bahasa terdeteksi.

        Penyedia asinkron (polling) wajib mengecek `should_cancel` dan melempar `JobCancelled`.
        """
