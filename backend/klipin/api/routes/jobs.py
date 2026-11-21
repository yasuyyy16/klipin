from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from klipin import jobs, usage
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.jobs import (
    JobConfirmRequest,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
    JobRetryResponse,
    UsageEstimate,
)
from klipin.db.models import Job, SourceStream

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


def _with_titles(db: Session, jobs_: list[Job], model: type[JobResponse]) -> list:
    """Tambahkan judul Stream Sumber agar P-06 bisa menampilkan objek tiap Job."""
    ids = {j.source_stream_id for j in jobs_ if j.source_stream_id}
    titles = dict(db.execute(select(SourceStream.id, SourceStream.title)
                             .where(SourceStream.id.in_(ids))).all()) if ids else {}
    return [model.model_validate(j).model_copy(update={"stream_title": titles.get(
        j.source_stream_id)}) for j in jobs_]


@router.get("")
def list_jobs(db: DbSession, status: str | None = None, source_stream_id: int | None = None,
              limit: Annotated[int, Query(ge=1, le=200)] = 50,
              offset: Annotated[int, Query(ge=0)] = 0) -> JobListResponse:
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    if statuses and not set(statuses) <= JOB_STATUSES:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.",
                       {"status": "Nilai tidak valid."})
    items, total = jobs.list_jobs(db, statuses, source_stream_id, limit, offset)
    return JobListResponse(items=_with_titles(db, items, JobResponse), total=total)


@router.get("/{job_id}")
def get_job(job_id: int, db: DbSession) -> JobDetailResponse:
    job = jobs.get_job(db, job_id)
    detail = _with_titles(db, [job], JobDetailResponse)[0]
    if job.job_type == "transcribe" and job.awaiting_confirmation and job.source_stream_id:
        estimate = usage.usage_estimate(db.connection(), job.source_stream_id,
                                        (job.checkpoint or {}).get("range"))
        detail = detail.model_copy(update={"usage_estimate": UsageEstimate(**estimate)})
    return detail


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: DbSession) -> JobResponse:
    return JobResponse.model_validate(jobs.cancel_job(db, job_id))


@router.post("/{job_id}/retry", status_code=202)
def retry_job(job_id: int, db: DbSession) -> JobRetryResponse:
    return JobRetryResponse(job=JobResponse.model_validate(jobs.retry_job(db, job_id)))


@router.post("/{job_id}/confirm")
def confirm_job(job_id: int, body: JobConfirmRequest, db: DbSession) -> JobResponse:
    job = jobs.confirm_job(db, job_id, body.proceed,
                           body.range.model_dump() if body.range else None)
    return JobResponse.model_validate(job)
