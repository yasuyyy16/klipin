"""Sinyal Chat (FR-010): pesan per 10 detik → dibanding median 5 menit sekitarnya → 0–1.

- Waktu pesan digeser mundur sebesar Jeda Chat (`chat_delay_ms`, default 8 detik) karena chat
  tertinggal dari kejadian; pesan dengan offset < 0 setelah digeser diabaikan.
- Pesan berkata/emote reaksi berbobot 1,5×. Reaksi dihitung ulang dari teks memakai daftar
  `chat_reaction_words` saat ini, agar perubahan di Pengaturan langsung berlaku.
- Rasio = jumlah berbobot ember ÷ median ember dalam ±150 detik (min. 1 pesan).
  Sinyal = (rasio − 1) / 4, dibatasi 0–1: setara median = 0, 5× median = 1.
- Sinyal jendela = ember tertinggi yang beririsan dengan jendela.
- Tanpa Pesan Chat → `None` ("tidak tersedia", BR-002).
"""

from collections.abc import Iterable

import numpy as np
from sqlalchemy import Connection, text

from klipin import app_settings
from klipin.media.chat_replay import reaction_matcher

BUCKET_MS = 10_000
MEDIAN_SPAN_MS = 300_000  # 5 menit di sekitar ember (±150 detik)
REACTION_WEIGHT = 1.5
FULL_RATIO = 5.0
MIN_MEDIAN = 1.0


def bucket_counts(messages: Iterable[tuple[int, bool]], duration_ms: int,
                  delay_ms: int = 8000) -> np.ndarray:
    """Jumlah pesan berbobot per ember 10 detik setelah digeser mundur `delay_ms`."""
    n = max(1, -(-duration_ms // BUCKET_MS))
    counts = np.zeros(n)
    for offset_ms, is_reaction in messages:
        t = offset_ms - delay_ms
        if 0 <= t < n * BUCKET_MS:
            counts[t // BUCKET_MS] += REACTION_WEIGHT if is_reaction else 1.0
    return counts


def spike_signal(counts: np.ndarray) -> np.ndarray:
    """Sinyal per ember (0–1) dari jumlah berbobot per ember."""
    half = MEDIAN_SPAN_MS // BUCKET_MS // 2
    out = np.zeros(len(counts))
    for i in range(len(counts)):
        med = float(np.median(counts[max(0, i - half):i + half + 1]))
        ratio = counts[i] / max(med, MIN_MEDIAN)
        out[i] = (ratio - 1) / (FULL_RATIO - 1)
    return np.clip(out, 0.0, 1.0)


def window_signal(per_bucket: np.ndarray | None, start_ms: int, end_ms: int) -> float | None:
    if per_bucket is None:
        return None
    lo, hi = start_ms // BUCKET_MS, max(start_ms // BUCKET_MS + 1, -(-end_ms // BUCKET_MS))
    part = per_bucket[lo:hi]
    return float(part.max()) if len(part) else 0.0


def stream_chat_signal(conn: Connection, stream_id: int, duration_ms: int) -> np.ndarray | None:
    """Sinyal Chat per ember untuk Stream Sumber; `None` bila tidak ada Pesan Chat."""
    has_chat = conn.execute(text("SELECT has_chat FROM source_streams WHERE id = :s"),
                            {"s": stream_id}).scalar()
    if not has_chat:
        return None
    rows = conn.execute(text("SELECT offset_ms, message FROM chat_messages "
                             "WHERE source_stream_id = :s"), {"s": stream_id}).all()
    if not rows:
        return None
    is_reaction = reaction_matcher(app_settings.value(conn, "chat_reaction_words", []) or [])
    delay = int(app_settings.value(conn, "chat_delay_ms", 8000) or 0)
    counts = bucket_counts(((o, is_reaction(m)) for o, m in rows), duration_ms, delay)
    return spike_signal(counts)
