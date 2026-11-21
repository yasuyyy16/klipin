"""Puncak amplitudo audio untuk trimmer P-05 (`GET /streams/{id}/waveform`, FR-015).

PCM mono 8 kHz dari FFmpeg di [from, to), dibagi `points` ember, nilai = |sampel| maksimum ÷ 32768
(0–1). Hasil di-cache per rentang di `streams/{id}/cache/`.
"""

import itertools
import json
import subprocess
from pathlib import Path

import numpy as np

from klipin.media.probe import ffmpeg_bin

SAMPLE_RATE = 8000
MAX_RANGE_MS = 10 * 60_000
MAX_POINTS = 4000


def peaks(src: Path, from_ms: int, to_ms: int, points: int, cache_dir: Path | None = None,
          timeout_s: float = 60) -> list[float]:
    cache = cache_dir / f"waveform_{from_ms}_{to_ms}_{points}.json" if cache_dir else None
    if cache and cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    result = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin",
         "-ss", f"{from_ms / 1000:.3f}", "-t", f"{(to_ms - from_ms) / 1000:.3f}", "-i", str(src),
         "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"],
        capture_output=True, timeout=timeout_s, check=False)
    samples = np.abs(np.frombuffer(result.stdout[: len(result.stdout) // 2 * 2], dtype=np.int16)
                     .astype(np.int32))
    out = []
    if samples.size:
        edges = np.linspace(0, samples.size, points + 1).astype(int)
        out = [round(float(samples[a:b].max()) / 32768, 4) if b > a else 0.0
               for a, b in itertools.pairwise(edges)]
    else:
        out = [0.0] * points  # tanpa trek audio
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
    return out
