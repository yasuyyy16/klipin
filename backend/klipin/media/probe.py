"""Lokasi FFmpeg/FFprobe (env `KLIPIN_FFMPEG_PATH` atau PATH) dan durasi media via FFprobe."""

import json
import subprocess
from pathlib import Path

from klipin.config import get_config
from klipin.doctor import find_ffmpeg

MSG_NO_FFMPEG = "FFmpeg tidak ditemukan. Jalankan `klipin doctor` untuk mengeceknya."


def ffmpeg_bin() -> str:
    ffmpeg, _ = find_ffmpeg(get_config())
    if not ffmpeg:
        raise RuntimeError(MSG_NO_FFMPEG)
    return ffmpeg


def ffprobe_bin() -> str:
    _, ffprobe = find_ffmpeg(get_config())
    if not ffprobe:
        raise RuntimeError(MSG_NO_FFMPEG)
    return ffprobe


def duration_ms(path: Path) -> int:
    """Durasi container dalam milidetik. Gagal baca → `ValueError`."""
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "json",
         str(path)], capture_output=True, text=True, timeout=60, check=False)
    try:
        return round(float(json.loads(out.stdout)["format"]["duration"]) * 1000)
    except (ValueError, KeyError, TypeError):
        raise ValueError(f"durasi tidak terbaca: {path}: {out.stderr.strip()[:300]}") from None
