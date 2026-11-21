"""Pengambil media palsu untuk `KLIPIN_PROVIDERS=fake` (uji UI/E2E tanpa jaringan).

Semua URL YouTube/Kick yang sah dijawab dari `tests/fixtures/ytdlp/*.json`: ID video diambil
dari URL, URL yang mengandung "live" dianggap sedang live, durasi 30 detik. Unduhan menyalin
`gaming_facecam_30s.mp4` + `live_chat_spike.jsonl` ke folder Stream Sumber.
"""

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from klipin.config import ROOT_DIR
from klipin.media import ytdlp
from klipin.worker.process import JobCancelled

FIXTURES = ROOT_DIR / "tests" / "fixtures"
VIDEO = FIXTURES / "gaming_facecam_30s.mp4"
CHAT = FIXTURES / "live_chat_spike.jsonl"
DURATION_S = 30
STEPS = 10
STEP_S = 0.2  # unduhan palsu ±2 detik agar progres terlihat di UI


def _fixture(name: str) -> Path:
    path = FIXTURES / name
    if not path.is_file():
        raise RuntimeError(f"Fixture mode fake tidak ditemukan: {path}")
    return path


def video_id(url: str) -> str:
    parts = urlsplit(url.strip())
    if v := parse_qs(parts.query).get("v"):
        return v[0]
    segments = [s for s in parts.path.split("/") if s]
    if segments:
        return segments[-1]
    return hashlib.sha1(url.encode()).hexdigest()[:11]


def inspect(url: str) -> ytdlp.InspectResult:
    platform = ytdlp.platform_of(url)
    live = "live" in url.lower()
    name = "youtube_live.json" if live else (
        "kick_vod.json" if platform == "kick" else "youtube_vod_chat.json")
    info = json.loads(_fixture(f"ytdlp/{name}").read_text(encoding="utf-8"))
    info.pop("requested_formats", None)
    info.update({
        "id": video_id(url), "webpage_url": url.strip(),
        "extractor_key": ("Kick" if live else "KickVOD") if platform == "kick" else "Youtube",
        "duration": None if live else DURATION_S,
        "filesize": None if live else _fixture(VIDEO.name).stat().st_size,
    })
    return ytdlp.result_from_info(info, platform)


def _check(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel and should_cancel():
        raise JobCancelled


def download_vod(url: str, dest_dir: Path, *,
                 on_progress: Callable[[int], None] | None = None,
                 should_cancel: Callable[[], bool] | None = None,
                 **_: object) -> ytdlp.DownloadResult:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for step in range(STEPS):
        _check(should_cancel)
        if on_progress:
            on_progress(step * 100 // STEPS)
        time.sleep(STEP_S)
    _check(should_cancel)
    target = dest_dir / "source.mp4"
    shutil.copyfile(_fixture(VIDEO.name), target)
    if on_progress:
        on_progress(100)
    return ytdlp.DownloadResult(path=target, width=960, height=540, fps=30.0)


def download_live_chat(url: str, dest_dir: Path, *,
                       should_cancel: Callable[[], bool] | None = None,
                       **_: object) -> Path | None:
    _check(should_cancel)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copyfile(_fixture(CHAT.name), dest_dir / "chat.json"))
