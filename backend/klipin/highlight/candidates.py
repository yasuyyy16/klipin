"""Pilih Kandidat Klip `auto` dari jendela berskor (FR-012, BR-004, BR-005, BR-006). Murni, tanpa I/O.

- Rentang: saran LLM (detik relatif awal jendela) bila ada, selain itu batas jendela. Dikoreksi
  (BR-004): dijepit ke jendela, lalu diperpanjang simetris ke ≥ 15 detik atau dipendekkan ke
  ≤ 90 detik, tetap di dalam [awal, akhir] rentang stream.
- Non-overlap (BR-005): urut skor turun; kandidat ditolak bila tumpang tindih > 5 detik dengan
  kandidat terpilih atau Klip `auto` yang dipertahankan (sudah direview).
- Jumlah (BR-006): min(20, maks(3, ceil(durasi_jam × 5))), hanya skor ≥ ambang (default 40).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

MIN_MS, MAX_MS = 15_000, 90_000
MAX_OVERLAP_MS = 5_000
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class Scored:
    window_start_ms: int
    window_end_ms: int
    score: int
    partial: bool
    suggested_start_s: float | None = None
    suggested_end_s: float | None = None
    payload: object = None  # data tambahan (sinyal, kategori, judul) untuk pembuat Klip


@dataclass(frozen=True)
class Candidate:
    start_ms: int
    end_ms: int
    source: Scored


def max_candidates(duration_ms: int) -> int:
    return min(20, max(3, math.ceil(duration_ms / HOUR_MS * 5)))


def correct_range(s: Scored, bounds: tuple[int, int]) -> tuple[int, int]:
    """Rentang Klip ≥ 15 & ≤ 90 detik di dalam jendela bila mungkin, selalu di dalam `bounds`."""
    lo_b, hi_b = bounds
    w0, w1 = s.window_start_ms, s.window_end_ms
    if s.suggested_start_s is not None and s.suggested_end_s is not None:
        start = w0 + round(s.suggested_start_s * 1000)
        end = w0 + round(s.suggested_end_s * 1000)
        start, end = max(w0, min(start, w1)), max(w0, min(end, w1))
        if end <= start:
            start, end = w0, w1
    else:
        start, end = w0, w1
    if end - start > MAX_MS:
        mid = (start + end) // 2
        start, end = mid - MAX_MS // 2, mid + MAX_MS // 2
    if end - start < MIN_MS:
        need = MIN_MS - (end - start)
        start -= need // 2
        end += need - need // 2
        if w1 - w0 >= MIN_MS:  # jendela cukup panjang: geser masuk ke jendela
            if start < w0:
                end, start = end + (w0 - start), w0
            if end > w1:
                start, end = start - (end - w1), w1
    # geser masuk ke rentang stream tanpa mengubah durasi (kecuali stream lebih pendek)
    if start < lo_b:
        end += lo_b - start
        start = lo_b
    if end > hi_b:
        start -= end - hi_b
        end = hi_b
    return max(lo_b, start), min(hi_b, end)


def overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def select(scored: Sequence[Scored], bounds: tuple[int, int], duration_ms: int, threshold: int,
           occupied: Sequence[tuple[int, int]] = ()) -> list[Candidate]:
    """Kandidat urut skor turun (seri: lebih awal dulu)."""
    taken: list[tuple[int, int]] = list(occupied)
    out: list[Candidate] = []
    limit = max_candidates(duration_ms)
    for s in sorted(scored, key=lambda s: (-s.score, s.window_start_ms)):
        if len(out) >= limit or s.score < threshold:
            break
        rng = correct_range(s, bounds)
        if rng[1] - rng[0] < MIN_MS:  # stream lebih pendek dari 15 detik
            continue
        if all(overlap(rng, t) <= MAX_OVERLAP_MS for t in taken):
            taken.append(rng)
            out.append(Candidate(rng[0], rng[1], s))
    return out
