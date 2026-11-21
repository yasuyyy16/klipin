"""Klip & data review stream (FR-014, FR-015)."""

from typing import Annotated

from fastapi import APIRouter, Query

from klipin import clips
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.routes.media import stream_video
from klipin.api.schemas.clips import NOT_NULLABLE, ClipCreateRequest, ClipPatchRequest, SnapRequest
from klipin.config import get_config
from klipin.media import waveform

router = APIRouter(prefix="/api/v1", tags=["clips"])


@router.get("/streams/{stream_id}/clips")
def list_stream_clips(stream_id: int, db: DbSession, status: str | None = None,
                      sort: Annotated[str, Query(pattern="^(score|start)$")] = "score",
                      limit: Annotated[int, Query(ge=1, le=200)] = 50,
                      offset: Annotated[int, Query(ge=0)] = 0) -> dict:
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    if statuses and not set(statuses) <= clips.CLIP_STATUSES:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.",
                       {"status": "Nilai tidak valid."})
    items, total = clips.list_clips(db, stream_id, statuses, sort, limit, offset)
    return {"items": items, "total": total}


@router.post("/streams/{stream_id}/clips", status_code=201)
def create_manual_clip(stream_id: int, body: ClipCreateRequest, db: DbSession) -> dict:
    clip = clips.create_manual(db, stream_id, body.start_ms, body.end_ms)
    return clips.detail(db, clip)


@router.get("/clips/{clip_id}")
def get_clip(clip_id: int, db: DbSession) -> dict:
    return clips.detail(db, clips.get_clip(db, clip_id))


@router.patch("/clips/{clip_id}")
def patch_clip(clip_id: int, body: ClipPatchRequest, db: DbSession) -> dict:
    changes = body.model_dump(exclude_unset=True)
    nulls = {k: "Wajib diisi." for k in NOT_NULLABLE if k in changes and changes[k] is None}
    if nulls:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.", nulls)
    clip, warnings = clips.patch(db, clip_id, changes)
    return {**clips.detail(db, clip), "warnings": warnings}


def _transition(clip_id: int, action: str, db: DbSession) -> dict:
    clip = clips.transition(db, clip_id, action)
    return {"id": clip.id, "status": clip.status}


@router.post("/clips/{clip_id}/approve")
def approve(clip_id: int, db: DbSession) -> dict:
    return _transition(clip_id, "approve", db)


@router.post("/clips/{clip_id}/reject")
def reject(clip_id: int, db: DbSession) -> dict:
    return _transition(clip_id, "reject", db)


@router.post("/clips/{clip_id}/restore")
def restore(clip_id: int, db: DbSession) -> dict:
    return _transition(clip_id, "restore", db)


@router.post("/clips/{clip_id}/unapprove")
def unapprove(clip_id: int, db: DbSession) -> dict:
    return _transition(clip_id, "unapprove", db)


@router.post("/clips/{clip_id}/snap")
def snap(clip_id: int, body: SnapRequest, db: DbSession) -> dict:
    return clips.snap(db, clip_id, body.edge, body.position_ms)


@router.get("/streams/{stream_id}/transcript")
def stream_transcript(stream_id: int, db: DbSession, from_ms: Annotated[int, Query(ge=0)],
                      to_ms: Annotated[int, Query(gt=0)]) -> dict:
    return clips.transcript(db, stream_id, from_ms, to_ms)


@router.get("/streams/{stream_id}/timeline")
def stream_timeline(stream_id: int, db: DbSession,
                    bucket_ms: Annotated[int, Query(ge=1000, le=600_000)] = 30_000) -> dict:
    return clips.timeline(db, stream_id, bucket_ms)


@router.get("/streams/{stream_id}/waveform")
def stream_waveform(stream_id: int, db: DbSession, from_ms: Annotated[int, Query(ge=0)],
                    to_ms: Annotated[int, Query(gt=0)],
                    points: Annotated[int, Query(ge=1, le=waveform.MAX_POINTS)] = 1200) -> dict:
    if to_ms <= from_ms or to_ms - from_ms > waveform.MAX_RANGE_MS:
        msg = "Rentang waveform maksimal 10 menit."
        raise ApiError(400, "VALIDATION_ERROR", msg, {"to_ms": msg})
    _, video = stream_video(db, stream_id)
    cache = get_config().klipin_home / "streams" / str(stream_id) / "cache"
    return {"from_ms": from_ms, "to_ms": to_ms,
            "peaks": waveform.peaks(video, from_ms, to_ms, points, cache)}
