"""Stream Sumber dari URL: inspect, buat (mode `vod`), daftar, detail (FR-001, FR-024)."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from klipin.api.errors import ApiError
from klipin.config import get_config
from klipin.db.models import Channel, Clip, Job, LayoutPreset, SourceStream
from klipin.media import fake as fake_media
from klipin.media import ytdlp
from klipin.worker import pipeline

log = structlog.get_logger(__name__)

INSPECT_TIMEOUT_S = 10  # 06-api.md §4
DISK_FACTOR = 1.5  # FR-001: butuh ruang ≥ perkiraan ukuran × 1,5
CLIP_STATUSES = ("candidate", "approved", "rejected", "rendering", "rendered", "render_failed")
MSG_STILL_LIVE = "Stream ini masih live. Gunakan Rekam Live?"
MSG_DUPLICATE = "Video ini sudah pernah diimpor."
MSG_TIMEOUT = "yt-dlp tidak menjawab dalam 10 detik. Coba lagi."

# 06-api.md §4: maks. 1 inspect berjalan sekaligus; request berikutnya menunggu giliran.
_inspect_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inspect")


def disk_free_bytes(path: Path) -> int:
    """Ruang kosong di drive folder kerja (folder terdekat yang sudah ada)."""
    while not path.exists() and path.parent != path:
        path = path.parent
    return shutil.disk_usage(path).free


def inspector():
    """yt-dlp asli, atau fixture saat `KLIPIN_PROVIDERS=fake` (tanpa jaringan)."""
    return fake_media.inspect if get_config().klipin_providers == "fake" else ytdlp.inspect


def run_inspect(url: str) -> ytdlp.InspectResult:
    """`ytdlp.inspect` dengan batas waktu & antrean satu-satu; error → `ApiError`."""
    try:
        ytdlp.platform_of(url)
        return _inspect_pool.submit(inspector(), url).result(timeout=INSPECT_TIMEOUT_S)
    except ytdlp.UrlNotSupportedError as e:
        raise ApiError(400, "URL_NOT_SUPPORTED", str(e)) from e
    except ytdlp.YtdlpError as e:
        raise ApiError(502, "UPSTREAM_ERROR", str(e)) from e
    except FutureTimeout as e:
        log.warning("inspect melewati batas waktu", url=url)
        raise ApiError(502, "UPSTREAM_ERROR", MSG_TIMEOUT) from e


def known_channel_id(session: Session, platform: str, external_id: str | None) -> int | None:
    if not external_id:
        return None
    return session.scalar(select(Channel.id).where(Channel.platform == platform,
                                                   Channel.external_id == external_id))


def _format_gb(n: int) -> str:
    return f"{n / 1e9:.1f}".replace(".", ",")


def check_disk(estimated_bytes: int | None, free_bytes: int) -> None:
    """FR-001: tolak bila ruang kosong < perkiraan × 1,5. Ukuran tak diketahui → lolos."""
    if estimated_bytes is None:
        return
    required = int(estimated_bytes * DISK_FACTOR)
    if free_bytes < required:
        raise ApiError(409, "INSUFFICIENT_DISK",
                       f"Butuh ±{_format_gb(required)} GB, tersedia {_format_gb(free_bytes)} GB. "
                       "Kosongkan ruang atau hapus video sumber lama.",
                       {"required_bytes": str(required), "free_bytes": str(free_bytes)})


def _find_or_create_channel(session: Session, info: ytdlp.InspectResult) -> int | None:
    if not info.channel_external_id:
        return None
    channel = session.scalar(select(Channel).where(
        Channel.platform == info.platform, Channel.external_id == info.channel_external_id))
    name = (info.channel_name or info.channel_external_id)[:200]
    if channel is None:
        channel = Channel(platform=info.platform, external_id=info.channel_external_id, name=name)
        session.add(channel)
        session.flush()
    elif channel.name != name:
        channel.name = name
    return channel.id


def create_vod(session: Session, url: str) -> tuple[SourceStream, Job]:
    """Buat Stream Sumber `vod_url` (`queued`) + Job `download` dalam satu transaksi."""
    info = run_inspect(url)
    if info.is_live:
        raise ApiError(409, "INVALID_STATE", MSG_STILL_LIVE)
    existing = session.scalar(select(SourceStream.id).where(
        SourceStream.platform == info.platform,
        SourceStream.external_video_id == info.external_video_id,
        SourceStream.status != "failed"))
    if existing is not None:
        raise ApiError(409, "INVALID_STATE", MSG_DUPLICATE,
                       {"existing_stream_id": str(existing)})
    check_disk(info.estimated_size_bytes, disk_free_bytes(get_config().klipin_home))

    stream = SourceStream(
        channel_id=_find_or_create_channel(session, info), source_type="vod_url",
        platform=info.platform, source_url=info.webpage_url or url.strip(),
        external_video_id=info.external_video_id, title=info.title,
        duration_ms=info.duration_ms, status="queued")
    session.add(stream)
    session.flush()
    job_id = pipeline.create_job(session.connection(), "download", stream.id)
    session.commit()
    log.info("stream dibuat", stream_id=stream.id, job_id=job_id, platform=info.platform)
    return stream, session.get(Job, job_id)


def get_stream(session: Session, stream_id: int) -> SourceStream:
    stream = session.get(SourceStream, stream_id)
    if stream is None:
        raise ApiError(404, "NOT_FOUND", "Stream Sumber tidak ditemukan.")
    return stream


def list_streams(session: Session, statuses: list[str] | None, limit: int,
                 offset: int) -> tuple[list[SourceStream], int]:
    query = select(SourceStream)
    if statuses:
        query = query.where(SourceStream.status.in_(statuses))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(query.order_by(SourceStream.created_at.desc(),
                                           SourceStream.id.desc()).limit(limit).offset(offset))
    return list(items), total


def _file_size(path: str | None) -> int:
    try:
        return Path(path).stat().st_size if path else 0
    except OSError:
        return 0


def summaries(session: Session, streams: list[SourceStream]) -> list[dict[str, Any]]:
    """Data ringkas per Stream Sumber untuk P-02: Kanal, jumlah Klip per status, ukuran file."""
    ids = [s.id for s in streams]
    channel_ids = {s.channel_id for s in streams if s.channel_id}
    channels = dict(session.execute(select(Channel.id, Channel.name)
                                    .where(Channel.id.in_(channel_ids))).all())
    counts: dict[int, dict[str, int]] = {i: dict.fromkeys(CLIP_STATUSES, 0) for i in ids}
    rendered: dict[int, int] = dict.fromkeys(ids, 0)
    for sid, status, n in session.execute(
            select(Clip.source_stream_id, Clip.status, func.count())
            .where(Clip.source_stream_id.in_(ids)).group_by(Clip.source_stream_id, Clip.status)):
        counts[sid][status] = n
    for sid, video, srt in session.execute(
            select(Clip.source_stream_id, Clip.output_video_path, Clip.output_srt_path)
            .where(Clip.source_stream_id.in_(ids), Clip.output_video_path.is_not(None))):
        rendered[sid] += _file_size(video) + _file_size(srt)
    return [{
        "id": s.id, "title": s.title, "platform": s.platform, "source_type": s.source_type,
        "status": s.status, "duration_ms": s.duration_ms, "error_message": s.error_message,
        "created_at": s.created_at, "channel_id": s.channel_id,
        "channel": {"id": s.channel_id, "name": channels[s.channel_id]}
        if s.channel_id in channels else None,
        "storage": {"source_bytes": 0 if s.source_deleted_at else _file_size(s.video_path),
                    "rendered_bytes": rendered[s.id],
                    "source_deleted": s.source_deleted_at is not None},
        "clip_counts": counts[s.id],
    } for s in streams]


def detail(session: Session, stream: SourceStream) -> dict[str, Any]:
    data = summaries(session, [stream])[0]
    preset = (session.get(LayoutPreset, stream.suggested_layout_preset_id)
              if stream.suggested_layout_preset_id else None)
    active = session.scalars(select(Job).where(
        Job.source_stream_id == stream.id, Job.status.in_(("queued", "running")))
        .order_by(Job.created_at, Job.id))
    return {
        **data,
        "source_url": stream.source_url,
        "detected_language": stream.detected_language,
        "has_chat": bool(stream.has_chat),
        "suggested_layout_preset": {"id": preset.id, "code": preset.code} if preset else None,
        "active_jobs": [{"id": j.id, "job_type": j.job_type, "status": j.status,
                         "progress_pct": j.progress_pct, "stage": j.stage,
                         "awaiting_confirmation": bool(j.awaiting_confirmation)}
                        for j in active],
    }


def inspect_response(session: Session, url: str) -> dict[str, Any]:
    info = run_inspect(url)
    return {
        "platform": info.platform,
        "external_video_id": info.external_video_id,
        "title": info.title,
        "channel": {"external_id": info.channel_external_id, "name": info.channel_name,
                    "known_channel_id": known_channel_id(session, info.platform,
                                                         info.channel_external_id)},
        "duration_ms": info.duration_ms,
        "is_live": info.is_live,
        "has_chat_replay": info.has_chat_replay,
        "estimated_size_bytes": info.estimated_size_bytes,
        "disk_free_bytes": disk_free_bytes(get_config().klipin_home),
    }

