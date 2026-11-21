"""Media dari disk lokal (06-api.md §3 `GET /media/...`). Path selalu dari ID di DB."""

import subprocess
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import Response

from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.db.models import SourceStream
from klipin.media.probe import ffmpeg_bin

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/media", tags=["media"])
FRAME_TIMEOUT_S = 15
MSG_SOURCE_DELETED = "Video sumber sudah dihapus."


def stream_video(db: DbSession, stream_id: int) -> tuple[SourceStream, Path]:
    stream = db.get(SourceStream, stream_id)
    if stream is None:
        raise ApiError(404, "NOT_FOUND", "Stream Sumber tidak ditemukan.")
    if stream.source_deleted_at:
        raise ApiError(409, "SOURCE_DELETED", MSG_SOURCE_DELETED)
    if not stream.video_path or not Path(stream.video_path).is_file():
        raise ApiError(409, "INVALID_STATE", "Video sumber belum tersedia.")
    return stream, Path(stream.video_path)


@router.get("/streams/{stream_id}/frame")
def stream_frame(stream_id: int, db: DbSession,
                 t_ms: Annotated[int, Query(ge=0)] = 0,
                 w: Annotated[int, Query(ge=16, le=1280)] = 640) -> Response:
    """Satu frame JPEG pada `t_ms` (FFmpeg seek), lebar `w` px (≤ 1280), cache 60 detik."""
    stream, video = stream_video(db, stream_id)
    if stream.duration_ms is not None and t_ms > stream.duration_ms:
        raise ApiError(400, "VALIDATION_ERROR", "Waktu di luar durasi video.",
                       {"t_ms": "Waktu di luar durasi video."})
    width = w - w % 2
    result = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{t_ms / 1000:.3f}",
         "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", "-c:v", "mjpeg",
         "-q:v", "4", "-f", "image2", "pipe:1"],
        capture_output=True, timeout=FRAME_TIMEOUT_S, check=False)
    if result.returncode != 0 or not result.stdout:
        log.warning("frame gagal", stream_id=stream_id, t_ms=t_ms,
                    error=result.stderr.decode(errors="replace")[-300:])
        raise ApiError(502, "UPSTREAM_ERROR", "Frame tidak bisa dibuat dari video sumber.")
    return Response(result.stdout, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=60"})
