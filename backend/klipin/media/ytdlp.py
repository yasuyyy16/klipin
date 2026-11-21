"""INT-01: yt-dlp untuk cek URL (`inspect`) dan unduh VOD ≤ 1080p ke MP4 (FR-001).

Rekam live (`record_live`) dan chat replay (INT-02) ada di task masing-masing (T-051, T-023).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import structlog
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled, YoutubeDLError

from klipin.config import get_config
from klipin.worker.process import JobCancelled

log = structlog.get_logger(__name__)

VOD_FORMAT = "bv*[height<=1080]+ba/b[height<=1080]"
MSG_URL_NOT_SUPPORTED = "URL tidak dikenali. Gunakan link VOD YouTube atau Kick."
MSG_YTDLP_FAILED = "Gagal membaca video. Situs mungkin berubah, coba Perbarui yt-dlp di Pengaturan."

_HOSTS = {
    "youtube.com": "youtube", "www.youtube.com": "youtube", "m.youtube.com": "youtube",
    "music.youtube.com": "youtube", "youtu.be": "youtube",
    "kick.com": "kick", "www.kick.com": "kick",
}
# extractor_key yt-dlp yang menghasilkan satu video, per platform
_EXTRACTORS = {"youtube": {"Youtube"}, "kick": {"Kick", "KickVOD"}}


class UrlNotSupportedError(Exception):
    """URL bukan video YouTube/Kick (06-api.md `URL_NOT_SUPPORTED`)."""

    def __init__(self) -> None:
        super().__init__(MSG_URL_NOT_SUPPORTED)


class YtdlpError(Exception):
    """yt-dlp gagal (06-api.md `UPSTREAM_ERROR`); `detail` hanya untuk log."""

    def __init__(self, detail: str) -> None:
        super().__init__(MSG_YTDLP_FAILED)
        self.detail = detail


@dataclass(frozen=True)
class InspectResult:
    platform: str
    external_video_id: str
    title: str
    channel_external_id: str | None
    channel_name: str | None
    duration_ms: int | None
    is_live: bool
    live_status: str | None
    has_chat_replay: bool
    estimated_size_bytes: int | None
    webpage_url: str | None


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    width: int | None
    height: int | None
    fps: float | None


def platform_of(url: str) -> str:
    """`youtube` atau `kick` dari host URL; selain itu `UrlNotSupportedError`."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        raise UrlNotSupportedError from None
    if parts.scheme not in {"http", "https"} or host not in _HOSTS:
        raise UrlNotSupportedError
    return _HOSTS[host]


class _Logger:
    """Teruskan keluaran yt-dlp ke log terstruktur, bukan stdout."""

    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            log.debug("yt-dlp", msg=msg)

    def info(self, msg: str) -> None:
        log.debug("yt-dlp", msg=msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp", msg=msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp", msg=msg)


def _base_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "format": VOD_FORMAT,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "logger": _Logger(),
    }
    ffmpeg = get_config().klipin_ffmpeg_path
    if ffmpeg:
        opts["ffmpeg_location"] = str(ffmpeg)
    return opts


def _estimate_size(info: dict[str, Any]) -> int | None:
    """Jumlah ukuran format terpilih; `None` bila ada yang tidak diketahui (mis. live)."""
    formats = info.get("requested_formats") or ([info] if info.get("format_id") else [])
    duration = info.get("duration")
    total = 0
    for f in formats:
        size = f.get("filesize") or f.get("filesize_approx")
        if not size and f.get("tbr") and duration:
            size = f["tbr"] * 1000 / 8 * duration  # tbr dalam kbit/s
        if not size:
            return None
        total += int(size)
    return total or None


def result_from_info(info: dict[str, Any], platform: str) -> InspectResult:
    """Ubah info dict yt-dlp menjadi `InspectResult`; tolak playlist/kanal/situs lain."""
    if (info.get("_type") not in {None, "video"} or not info.get("id")
            or info.get("extractor_key") not in _EXTRACTORS[platform]):
        raise UrlNotSupportedError
    live_status = info.get("live_status")
    duration = info.get("duration")
    channel_id = info.get("channel_id") or info.get("uploader_id")
    return InspectResult(
        platform=platform,
        external_video_id=str(info["id"]),
        title=(info.get("title") or str(info["id"]))[:500],
        channel_external_id=str(channel_id) if channel_id else None,
        channel_name=info.get("channel") or info.get("uploader"),
        duration_ms=round(duration * 1000) if duration else None,
        is_live=live_status == "is_live" or info.get("is_live") is True,
        live_status=live_status,
        has_chat_replay="live_chat" in (info.get("subtitles") or {}),
        estimated_size_bytes=_estimate_size(info),
        webpage_url=info.get("webpage_url"),
    )


def inspect(url: str, *, ydl_cls: type[YoutubeDL] = YoutubeDL) -> InspectResult:
    """Ambil metadata tanpa mengunduh. Error: `UrlNotSupportedError`, `YtdlpError`."""
    platform = platform_of(url)
    try:
        with ydl_cls({**_base_opts(), "skip_download": True}) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
    except YoutubeDLError as e:
        if "Unsupported URL" in str(e):
            raise UrlNotSupportedError from e
        log.warning("inspect gagal", url=url, error=str(e))
        raise YtdlpError(str(e)) from e
    return result_from_info(info, platform)


class _Progress:
    """Hook progres yt-dlp → persen gabungan semua format (video + audio), plus cek batal."""

    def __init__(self, on_progress: Callable[[int], None] | None,
                 should_cancel: Callable[[], bool] | None) -> None:
        self.on_progress = on_progress
        self.should_cancel = should_cancel
        self.finished: set[str] = set()
        self.last_pct = -1

    def hook(self, d: dict[str, Any]) -> None:
        if self.should_cancel and self.should_cancel():
            raise DownloadCancelled("Job dibatalkan")
        n_files = len(d.get("info_dict", {}).get("requested_formats") or ()) or 1
        frac = 0.0
        if d["status"] == "finished":
            self.finished.add(d.get("filename", ""))
        elif d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                frac = d.get("downloaded_bytes", 0) / total
            elif d.get("fragment_count"):
                frac = d.get("fragment_index", 0) / d["fragment_count"]
        pct = int(min(len(self.finished) + min(frac, 1.0), n_files) / n_files * 100)
        if self.on_progress and pct != self.last_pct:
            self.last_pct = pct
            self.on_progress(pct)


def download_vod(
    url: str,
    dest_dir: Path,
    *,
    on_progress: Callable[[int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    info: dict[str, Any] | None = None,
    ydl_cls: type[YoutubeDL] = YoutubeDL,
) -> DownloadResult:
    """Unduh VOD ke `{dest_dir}/source.mp4`; file `.part` yang ada dilanjutkan (`continuedl`).

    `info` = info dict yt-dlp yang sudah diekstrak (mis. tersimpan); bila diisi, ekstraksi
    ulang dilewati. Batal (`should_cancel`) → `JobCancelled`; gagal → `YtdlpError`.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    progress = _Progress(on_progress, should_cancel)
    opts = {
        **_base_opts(),
        "outtmpl": {"default": str(dest_dir / "source.%(ext)s")},
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "continuedl": True,
        "progress_hooks": [progress.hook],
    }
    try:
        with ydl_cls(opts) as ydl:
            if info is None:
                result = ydl.extract_info(url, download=True)
            else:
                result = ydl.process_ie_result(dict(info), download=True)
    except DownloadCancelled as e:
        raise JobCancelled from e
    except YoutubeDLError as e:
        log.warning("unduh gagal", url=url, error=str(e))
        raise YtdlpError(str(e)) from e
    downloaded = (result.get("requested_downloads") or [result])[0]
    path = Path(downloaded.get("filepath") or downloaded.get("_filename") or "")
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise YtdlpError(f"hasil unduhan tidak ditemukan: {path}")
    fps = downloaded.get("fps")
    return DownloadResult(path=path, width=downloaded.get("width"),
                          height=downloaded.get("height"), fps=float(fps) if fps else None)


def download_live_chat(
    url: str,
    dest_dir: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
    ydl_cls: type[YoutubeDL] = YoutubeDL,
) -> Path | None:
    """INT-02: unduh chat replay YouTube (`live_chat`, JSON-lines) ke `{dest_dir}/chat.json`.

    `None` bila video tidak punya chat replay. Batal → `JobCancelled`; gagal → `YtdlpError`.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    progress = _Progress(None, should_cancel)
    opts = {
        **_base_opts(),
        "skip_download": True,
        "writesubtitles": True,
        "subtitleslangs": ["live_chat"],
        "outtmpl": {"default": str(dest_dir / "chat.%(ext)s")},
        "progress_hooks": [progress.hook],
    }
    try:
        with ydl_cls(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadCancelled as e:
        raise JobCancelled from e
    except YoutubeDLError as e:
        raise YtdlpError(str(e)) from e
    sub = (info.get("requested_subtitles") or {}).get("live_chat")
    if not sub or not sub.get("filepath") or not Path(sub["filepath"]).is_file():
        return None
    target = dest_dir / "chat.json"
    Path(sub["filepath"]).replace(target)
    return target
