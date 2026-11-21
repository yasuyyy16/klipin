"""Antarmuka `HighlightJudge` (ADR-003, INT-05 `judge_highlight`, FR-011).

Penilai menerima satu jendela (transkrip ±90 detik + angka Sinyal) dan mengembalikan
`JudgeResult`: `done` + `Judgement` tervalidasi, `invalid` (respons gagal validasi 2×), atau
`failed` (error sementara habis/penolakan). `JudgeUnavailable` = LLM tidak bisa dipakai sama
sekali (key/model/izin) → skor memakai Audio + Chat saja ("skor parsial", INT-05 Fallback).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["lucu", "hype", "kontroversial", "informatif", "emosional", "lainnya"]
CATEGORIES: tuple[str, ...] = ("lucu", "hype", "kontroversial", "informatif", "emosional",
                               "lainnya")
MSG_NO_KEY = "API key LLM belum diisi. Skor memakai Sinyal Audio dan Chat saja."
MSG_NO_MODEL = ("Model LLM untuk menilai highlight belum dipilih di Pengaturan. "
                "Skor memakai Sinyal Audio dan Chat saja.")


@dataclass(frozen=True)
class WindowInput:
    """Satu jendela untuk dinilai. Waktu transkrip relatif awal `start_ms` (detik)."""

    key: int  # id jendela / indeks, untuk memetakan hasil
    start_ms: int
    end_ms: int
    language: str | None
    transcript: list[str]  # baris "[12.4] S1: teks"
    audio_signal: float
    chat_signal: float | None
    layout_preset: str | None = None


class Judgement(BaseModel):
    """Skema output `judge_highlight` (07-integrasi.md INT-05), batas mengikuti 05-database."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    category: Category
    reason: str = Field(min_length=1, max_length=200)
    suggested_start_s: float = Field(ge=0)
    suggested_end_s: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=100)


@dataclass
class JudgeResult:
    status: Literal["done", "invalid", "failed"]
    judgement: Judgement | None = None
    detail: str = ""
    attempts: int = 0
    extra: dict = field(default_factory=dict)


class JudgeUnavailable(Exception):
    """LLM tidak bisa dipakai untuk seluruh Job; `str(e)` = pesan Bahasa Indonesia."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class HighlightJudge(ABC):
    name: str

    @abstractmethod
    def judge(self, window: WindowInput, *,
              should_cancel: Callable[[], bool] | None = None) -> JudgeResult:
        """Nilai satu jendela (termasuk coba ulang validasi 1× & error sementara)."""
