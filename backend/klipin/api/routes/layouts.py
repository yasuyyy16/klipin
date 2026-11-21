"""Preset Layout, Kanal, dan Region Cam (FR-006, FR-007, FR-008)."""

from fastapi import APIRouter

from klipin import layouts, streams
from klipin.api.deps import DbSession
from klipin.api.schemas.layouts import (
    ChannelCreateRequest,
    ClipRegionsRequest,
    StreamChannelRequest,
)
from klipin.api.schemas.streams import StreamResponse

router = APIRouter(prefix="/api/v1", tags=["layouts"])


@router.get("/layout-presets")
def list_layout_presets(db: DbSession) -> dict:
    return {"items": layouts.list_presets(db)}


@router.get("/channels")
def list_channels(db: DbSession) -> dict:
    items = layouts.list_channels(db)
    return {"items": items, "total": len(items)}


@router.post("/channels", status_code=201)
def create_channel(body: ChannelCreateRequest, db: DbSession) -> dict:
    return layouts.create_channel(db, body.name)


@router.patch("/streams/{stream_id}/channel")
def set_stream_channel(stream_id: int, body: StreamChannelRequest, db: DbSession) -> dict:
    stream = layouts.set_stream_channel(db, stream_id, body.channel_id)
    return {"stream": StreamResponse.model_validate(streams.summaries(db, [stream])[0])}


@router.get("/streams/{stream_id}/regions")
def get_stream_regions(stream_id: int, db: DbSession) -> dict:
    return layouts.stream_regions(db, stream_id)


@router.put("/clips/{clip_id}/regions")
def put_clip_regions(clip_id: int, body: ClipRegionsRequest, db: DbSession) -> dict:
    return layouts.set_clip_regions(db, clip_id, [r.model_dump() for r in body.regions],
                                    body.save_as_channel_default, body.apply_to_stream_clips)
