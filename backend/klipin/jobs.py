"""Kontrol Job dari API: daftar, batal, coba ulang, konfirmasi (FR-022, FR-023)."""

from sqlalchemy import Connection, func, select, text
from sqlalchemy.orm import Session

from klipin.api.errors import ApiError
from klipin.db.models import Job, SourceStream, utcnow
from klipin.worker import pipeline

NEEDS_SOURCE_VIDEO = {"detect_layout", "transcribe", "score_highlights", "render"}
COPY_ON_RETRY = ("job_type", "source_stream_id", "clip_id", "upload_id", "purpose",
                 "preview_at_ms", "scope_start_ms", "scope_end_ms", "is_heavy", "priority",
                 "checkpoint")
CANCELLED_MESSAGE = "Job dibatalkan."


def _get(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Job tidak ditemukan.")
    return job


def list_jobs(session: Session, statuses: list[str] | None, stream_id: int | None,
              limit: int, offset: int) -> tuple[list[Job], int]:
    query = select(Job)
    if statuses:
        query = query.where(Job.status.in_(statuses))
    if stream_id is not None:
        query = query.where(Job.source_stream_id == stream_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(query.order_by(Job.created_at.desc(), Job.id.desc())
                            .limit(limit).offset(offset)).all()
    return list(items), total


def get_job(session: Session, job_id: int) -> Job:
    return _get(session, job_id)


def _set_clip_status(conn: Connection, clip_id: int, frm: str, to: str) -> None:
    conn.execute(text("UPDATE clips SET status = :to, updated_at = :now "
                      "WHERE id = :id AND status = :frm"),
                 {"to": to, "frm": frm, "id": clip_id, "now": utcnow()})


def cancel_job(session: Session, job_id: int) -> Job:
    job = _get(session, job_id)
    conn = session.connection()
    # shortcut: cancel record_live = "stop" (gabung segmen lalu lanjut pipeline) di T-051.
    updated = conn.execute(text(
        "UPDATE jobs SET status = 'cancelled', updated_at = :now, finished_at = CASE "
        "WHEN status = 'queued' THEN :now ELSE finished_at END "
        "WHERE id = :id AND status IN ('queued', 'running')"),
        {"id": job_id, "now": utcnow()}).rowcount
    if not updated:
        raise ApiError(409, "INVALID_STATE", "Job sudah selesai dan tidak bisa dibatalkan.")
    if job.job_type == "render" and job.purpose == "final" and job.clip_id:
        _set_clip_status(conn, job.clip_id, "rendering", "approved")
    pipeline.on_failed(conn, job, CANCELLED_MESSAGE)
    session.commit()
    session.refresh(job)
    return job


def retry_job(session: Session, job_id: int) -> Job:
    job = _get(session, job_id)
    if job.status not in ("failed", "cancelled"):
        raise ApiError(409, "INVALID_STATE",
                       "Hanya Job yang gagal atau dibatalkan yang bisa dicoba lagi.")
    pending_retry = session.scalar(select(Job.id).where(
        Job.retry_of_job_id == job_id, Job.status.in_(("queued", "running"))))
    if pending_retry is not None:
        raise ApiError(409, "INVALID_STATE", "Job ini sudah sedang dicoba lagi.")
    stream = session.get(SourceStream, job.source_stream_id) if job.source_stream_id else None
    if stream and stream.source_deleted_at and job.job_type in NEEDS_SOURCE_VIDEO:
        raise ApiError(409, "SOURCE_DELETED", "Video sumber sudah dihapus.")

    retry = Job(**{col: getattr(job, col) for col in COPY_ON_RETRY}, retry_of_job_id=job.id)
    session.add(retry)
    session.flush()
    conn = session.connection()
    if stream is not None and job.scope_start_ms is None:
        if job.job_type == "download":
            pipeline.set_stream_status(conn, stream.id, "queued")
        elif job.job_type in pipeline.PIPELINE_TYPES:
            pipeline.set_stream_status(conn, stream.id, "processing")
    if job.job_type == "render" and job.purpose == "final" and job.clip_id:
        _set_clip_status(conn, job.clip_id, "render_failed", "rendering")
    session.commit()
    session.refresh(retry)
    return retry


def confirm_job(session: Session, job_id: int, proceed: bool, has_range: bool) -> Job:
    job = _get(session, job_id)
    if job.job_type != "transcribe" or not job.awaiting_confirmation or job.status != "queued":
        raise ApiError(409, "INVALID_STATE", "Job ini tidak menunggu konfirmasi.")
    if has_range:
        # shortcut: konfirmasi dengan rentang + batas durasi per Job dibuat di T-030 (FR-022).
        raise ApiError(400, "VALIDATION_ERROR", "Konfirmasi dengan rentang belum didukung.",
                       {"range": "Konfirmasi dengan rentang belum didukung."})
    if proceed:
        job.awaiting_confirmation = 0
        session.commit()
        session.refresh(job)
    return job
