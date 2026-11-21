from pydantic import BaseModel, ConfigDict, Field, model_validator

from klipin.api.errors import user_error


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
    stream_title: str | None = None


class PricingLinks(BaseModel):
    transcriber: str | None
    llm: str | None


class UsageEstimate(BaseModel):
    """FR-022; `duration_ms`, `max_audio_ms`, `over_limit` melengkapi contoh 06-api.md."""

    audio_ms: int
    estimated_llm_windows: int
    duration_ms: int
    max_audio_ms: int
    over_limit: bool
    pricing_links: PricingLinks


class JobDetailResponse(JobResponse):
    log_tail: str | None
    usage_estimate: UsageEstimate | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class JobRetryResponse(BaseModel):
    job: JobResponse


class ConfirmRange(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "ConfirmRange":
        if self.end_ms <= self.start_ms:
            raise user_error("Waktu selesai harus setelah waktu mulai.")
        return self


class JobConfirmRequest(BaseModel):
    proceed: bool
    range: ConfirmRange | None = None
