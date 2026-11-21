"""Jendela penilaian & pra-seleksi LLM (FR-011, BR-003).

- Jendela 60 detik, geser 30 detik, di dalam rentang yang ditranskripsi (Job `transcribe`
  bisa dibatasi rentang saat konfirmasi pemakaian, FR-022). Jendela terakhir dipotong di akhir
  rentang; jendela < 15 detik (durasi Klip minimum, BR-004) tidak dibuat.
- Skor pra-seleksi = 0,6 × Audio + 0,4 × Chat (tanpa chat: Audio saja). Lolos bila ≥
  persentil 80, ditambah sampel acak 5% dari jendela lain (seed = id Stream Sumber agar hasil
  sama saat hitung ulang), maks. 120 jendela per jam stream (yang skornya tertinggi dipertahankan).
- Penyimpanan ke `highlight_windows` tidak menimpa hasil LLM (cache untuk "Hitung ulang skor").
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import Connection, text

from klipin.db.models import utcnow
from klipin.highlight import audio_signal, chat_signal

WINDOW_MS = 60_000
STEP_MS = 30_000
MIN_WINDOW_MS = 15_000
AUDIO_WEIGHT, CHAT_WEIGHT = 0.6, 0.4
PERCENTILE = 80
RANDOM_SHARE = 0.05
MAX_PER_HOUR = 120
HOUR_MS = 3_600_000


@dataclass
class Window:
    start_ms: int
    end_ms: int
    audio: float
    chat: float | None
    preselected: bool = False

    @property
    def pre_score(self) -> float:
        if self.chat is None:
            return self.audio
        return AUDIO_WEIGHT * self.audio + CHAT_WEIGHT * self.chat


def window_bounds(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    out = []
    t = start_ms
    while t < end_ms:
        end = min(t + WINDOW_MS, end_ms)
        if end - t >= MIN_WINDOW_MS or not out:
            out.append((t, end))
        if end >= end_ms:
            break
        t += STEP_MS
    return out


def build_windows(start_ms: int, end_ms: int, audio_per_second: np.ndarray,
                  chat_per_bucket: np.ndarray | None) -> list[Window]:
    return [Window(s, e, audio_signal.window_signal(audio_per_second, s, e),
                   chat_signal.window_signal(chat_per_bucket, s, e))
            for s, e in window_bounds(start_ms, end_ms)]


def max_windows(duration_ms: int) -> int:
    return max(1, math.ceil(duration_ms / HOUR_MS * MAX_PER_HOUR))


def preselect(windows: Sequence[Window], duration_ms: int, seed: int) -> list[Window]:
    """Tandai `preselected` sesuai BR-003; kembalikan jendela terpilih (urut prioritas)."""
    for w in windows:
        w.preselected = False
    if not windows:
        return []
    scores = np.array([w.pre_score for w in windows])
    threshold = float(np.percentile(scores, PERCENTILE))
    top = sorted((w for w in windows if w.pre_score >= threshold),
                 key=lambda w: (-w.pre_score, w.start_ms))
    rest = [w for w in windows if w.pre_score < threshold]
    extra_n = min(len(rest), math.ceil(len(rest) * RANDOM_SHARE))
    extra = random.Random(seed).sample(rest, extra_n) if extra_n else []
    chosen = (top + sorted(extra, key=lambda w: w.start_ms))[:max_windows(duration_ms)]
    for w in chosen:
        w.preselected = True
    return chosen


def store(conn: Connection, stream_id: int, windows: Sequence[Window]) -> None:
    """Upsert jendela; kolom `llm_*` jendela yang sudah ada dipertahankan (cache LLM)."""
    now = utcnow()
    starts = [w.start_ms for w in windows]
    if starts:
        conn.execute(text(
            "DELETE FROM highlight_windows WHERE source_stream_id = :s AND start_ms NOT IN ("
            + ",".join(str(s) for s in starts) + ")"), {"s": stream_id})
    else:
        conn.execute(text("DELETE FROM highlight_windows WHERE source_stream_id = :s"),
                     {"s": stream_id})
    for w in windows:
        conn.execute(text(
            "INSERT INTO highlight_windows (source_stream_id, start_ms, end_ms, audio_signal, "
            "chat_signal, preselected) VALUES (:s, :a, :b, :au, :ch, :p) "
            "ON CONFLICT (source_stream_id, start_ms) DO UPDATE SET end_ms = excluded.end_ms, "
            "audio_signal = excluded.audio_signal, chat_signal = excluded.chat_signal, "
            "preselected = excluded.preselected, updated_at = :now"),
            {"s": stream_id, "a": w.start_ms, "b": w.end_ms, "au": round(w.audio, 6),
             "ch": None if w.chat is None else round(w.chat, 6), "p": int(w.preselected),
             "now": now})
