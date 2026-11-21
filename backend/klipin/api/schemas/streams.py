from typing import Literal

from pydantic import BaseModel, Field

from klipin.api.schemas.jobs import JobResponse


class StreamInspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class InspectChannel(BaseModel):
    external_id: str | None
    name: str | None
    known_channel_id: int | None


class StreamInspectResponse(BaseModel):
    platform: str
    external_video_id: str
    title: str
    channel: InspectChannel
    duration_ms: int | None
    is_live: bool
    has_chat_replay: bool
    estimated_size_bytes: int | None
    disk_free_bytes: int


class StreamCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    mode: Literal["vod", "live"]
    live_analysis_enabled: bool = False


class ChannelRef(BaseModel):
    id: int
    name: str


class StreamStorage(BaseModel):
    source_bytes: int
    rendered_bytes: int
    source_deleted: bool


class StreamResponse(BaseModel):
    id: int
    title: str
    platform: str
    source_type: str
    status: str
    duration_ms: int | None
    error_message: str | None
    created_at: str
    channel_id: int | None
    channel: ChannelRef | None
    storage: StreamStorage
    clip_counts: dict[str, int]


class PresetRef(BaseModel):
    id: int
    code: str


class ActiveJob(BaseModel):
    id: int
    job_type: str
    status: str
    progress_pct: int
    stage: str | None
    awaiting_confirmation: bool


class StreamDetailResponse(StreamResponse):
    source_url: str | None
    detected_language: str | None
    has_chat: bool
    suggested_layout_preset: PresetRef | None
    active_jobs: list[ActiveJob]


class StreamListResponse(BaseModel):
    items: list[StreamResponse]
    total: int


class StreamCreateResponse(BaseModel):
    stream: StreamResponse
    job: JobResponse
