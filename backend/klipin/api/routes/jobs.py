from typing import Annotated

from fastapi import APIRouter, Query

from klipin import jobs
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.jobs import (
    JobConfirmRequest,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
    JobRetryResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


@router.get("")
def list_jobs(db: DbSession, status: str | None = None, source_stream_id: int | None = None,
              limit: Annotated[int, Query(ge=1, le=200)] = 50,
              offset: Annotated[int, Query(ge=0)] = 0) -> JobListResponse:
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    if statuses and not set(statuses) <= JOB_STATUSES:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.",
                       {"status": "Nilai tidak valid."})
    items, total = jobs.list_jobs(db, statuses, source_stream_id, limit, offset)
    return JobListResponse(items=[JobResponse.model_validate(j) for j in items], total=total)


@router.get("/{job_id}")
def get_job(job_id: int, db: DbSession) -> JobDetailResponse:
    # shortcut: usage_estimate untuk Job yang menunggu konfirmasi ditambahkan di T-030.
    return JobDetailResponse.model_validate(jobs.get_job(db, job_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: DbSession) -> JobResponse:
    return JobResponse.model_validate(jobs.cancel_job(db, job_id))


@router.post("/{job_id}/retry", status_code=202)
def retry_job(job_id: int, db: DbSession) -> JobRetryResponse:
    return JobRetryResponse(job=JobResponse.model_validate(jobs.retry_job(db, job_id)))


@router.post("/{job_id}/confirm")
def confirm_job(job_id: int, body: JobConfirmRequest, db: DbSession) -> JobResponse:
    job = jobs.confirm_job(db, job_id, body.proceed, body.range is not None)
    return JobResponse.model_validate(job)
