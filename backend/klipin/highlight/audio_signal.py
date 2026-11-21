"""Sinyal Audio (FR-009): loudness per detik → lonjakan terhadap 60 detik sebelumnya → 0–1.

1. FFmpeg mendekode audio ke PCM mono 8 kHz (pipe), NumPy menghitung RMS per 1 detik (dBFS).
2. Simpangan baku loudness seluruh Stream Sumber (z-score) menjadi satuan.
3. Kenaikan detik ini terhadap rata-rata 60 detik sebelumnya, dalam satuan simpangan baku.
   Sinyal = (kenaikan − 1σ) / 1,25σ, dibatasi 0–1: fluktuasi ≤ 1σ = 0 (audio tenang tetap
   rendah), kenaikan 2σ (batas "lonjakan" FR-009) = 0,8, ≥ 2,25σ = 1.
Sinyal jendela = nilai tertinggi per detik di dalam jendela (teriakan 1 detik tetap terhitung).
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import numpy as np

from klipin.media.probe import ffmpeg_bin
from klipin.worker.process import JobCancelled, kill_tree

SAMPLE_RATE = 8000
SILENCE_DB = -100.0
BASELINE_S = 60
NORMAL_SIGMA = 1.0  # fluktuasi wajar
SPAN_SIGMA = 1.25  # 1σ → 0, 2σ → 0,8, 2,25σ → 1
MIN_STD_DB = 1.0  # audio nyaris konstan: hindari pembagian dengan ~0


def loudness_db_per_second(src: Path, *, start_ms: int = 0, end_ms: int | None = None,
                           should_cancel: Callable[[], bool] | None = None) -> np.ndarray:
    """Loudness RMS (dBFS) tiap detik di [start_ms, end_ms). Tanpa trek audio → array kosong."""
    args = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start_ms:
        args += ["-ss", f"{start_ms / 1000:.3f}"]
    args += ["-i", str(src)]
    if end_ms is not None:
        args += ["-t", f"{(end_ms - start_ms) / 1000:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-acodec", "pcm_s16le",
             "pipe:1"]
    block = SAMPLE_RATE * 2  # 1 detik s16le
    values: list[float] = []
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        assert proc.stdout is not None
        while True:
            if should_cancel and should_cancel():
                kill_tree(proc)
                raise JobCancelled
            data = proc.stdout.read(block)
            if len(data) < 2:
                break
            samples = np.frombuffer(data[: len(data) // 2 * 2], dtype=np.int16).astype(np.float64)
            rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
            values.append(max(SILENCE_DB, 20 * np.log10(rms)) if rms > 0 else SILENCE_DB)
    finally:
        if proc.poll() is None:
            proc.wait(timeout=30)
    return np.asarray(values, dtype=np.float64)


def spike_signal(loudness_db: np.ndarray, baseline_s: int = BASELINE_S) -> np.ndarray:
    """Lonjakan per detik (0–1) dari loudness per detik."""
    n = len(loudness_db)
    if n == 0:
        return np.zeros(0)
    std = max(float(np.std(loudness_db)), MIN_STD_DB)
    csum = np.concatenate(([0.0], np.cumsum(loudness_db)))
    idx = np.arange(n)
    lo = np.maximum(0, idx - baseline_s)
    count = idx - lo
    # rata-rata 60 detik sebelumnya; detik pertama memakai dirinya sendiri (tanpa riwayat)
    prev_mean = np.where(count > 0, (csum[idx] - csum[lo]) / np.maximum(count, 1), loudness_db)
    rise = (loudness_db - prev_mean) / std
    return np.clip((rise - NORMAL_SIGMA) / SPAN_SIGMA, 0.0, 1.0)


def window_signal(per_second: np.ndarray, start_ms: int, end_ms: int) -> float:
    """Sinyal Audio satu jendela = nilai per detik tertinggi di [start_ms, end_ms)."""
    lo, hi = max(0, start_ms // 1000), max(start_ms // 1000 + 1, -(-end_ms // 1000))
    part = per_second[lo:hi]
    return float(part.max()) if len(part) else 0.0
