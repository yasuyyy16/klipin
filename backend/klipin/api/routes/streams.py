from typing import Annotated

from fastapi import APIRouter, Query

from klipin import streams
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.jobs import JobResponse
from klipin.api.schemas.streams import (
    StreamCreateRequest,
    StreamCreateResponse,
    StreamDetailResponse,
    StreamInspectRequest,
    StreamInspectResponse,
    StreamListResponse,
)

router = APIRouter(prefix="/api/v1/streams", tags=["streams"])
STREAM_STATUSES = {"queued", "downloading", "recording", "processing", "ready", "failed"}


@router.post("/inspect")
def inspect_stream(body: StreamInspectRequest, db: DbSession) -> StreamInspectResponse:
    return StreamInspectResponse.model_validate(streams.inspect_response(db, body.url))


@router.post("", status_code=201)
def create_stream(body: StreamCreateRequest, db: DbSession) -> StreamCreateResponse:
    if body.mode == "live":
        # shortcut: mode live (Job record_live) dibuat di T-051.
        raise ApiError(400, "VALIDATION_ERROR", "Rekam live belum tersedia di versi ini.",
                       {"mode": "Nilai tidak valid."})
    stream, job = streams.create_vod(db, body.url)
    return StreamCreateResponse(stream=streams.summaries(db, [stream])[0],
                                job=JobResponse.model_validate(job))


@router.get("")
def list_streams(db: DbSession, status: str | None = None,
                 limit: Annotated[int, Query(ge=1, le=200)] = 50,
                 offset: Annotated[int, Query(ge=0)] = 0) -> StreamListResponse:
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    if statuses and not set(statuses) <= STREAM_STATUSES:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.",
                       {"status": "Nilai tidak valid."})
    items, total = streams.list_streams(db, statuses, limit, offset)
    return StreamListResponse(items=streams.summaries(db, items), total=total)


@router.get("/{stream_id}")
def get_stream(stream_id: int, db: DbSession) -> StreamDetailResponse:
    return StreamDetailResponse.model_validate(
        streams.detail(db, streams.get_stream(db, stream_id)))


@router.post("/{stream_id}/rescore", status_code=202)
def rescore_stream(stream_id: int, db: DbSession) -> dict:
    return {"job": JobResponse.model_validate(streams.rescore(db, stream_id))}
