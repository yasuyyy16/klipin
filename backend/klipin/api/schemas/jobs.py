from pydantic import BaseModel, ConfigDict, Field


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    status: str
    source_stream_id: int | None
    clip_id: int | None
    upload_id: int | None
    purpose: str
    scope_start_ms: int | None
    scope_end_ms: int | None
    is_heavy: bool
    priority: int
    awaiting_confirmation: bool
    progress_pct: int
    stage: str | None
    error_message: str | None
    retry_of_job_id: int | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str


class JobDetailResponse(JobResponse):
    log_tail: str | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class JobRetryResponse(BaseModel):
    job: JobResponse


class ConfirmRange(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class JobConfirmRequest(BaseModel):
    proceed: bool
    range: ConfirmRange | None = None
