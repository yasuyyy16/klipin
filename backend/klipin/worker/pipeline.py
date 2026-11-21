"""Orkestrator pipeline: "Job X sukses → Job Y" (04-arsitektur.md §3.1) dan status Stream Sumber
(03-user-flow.md §4.1). Semua fungsi dipanggil di dalam transaksi pemanggil, sehingga Job
berikutnya dibuat atomik bersama penandaan status Job.
"""

from typing import Any, Protocol

import structlog
from sqlalchemy import Connection, text

from klipin import usage
from klipin.db.models import utcnow

log = structlog.get_logger(__name__)

STREAM_TRANSITIONS = {
    "queued": {"downloading"},
    "downloading": {"processing", "failed"},
    "recording": {"processing", "failed"},
    "processing": {"ready", "failed"},
    "ready": {"processing"},
    "failed": {"queued", "processing"},
}
# Job yang menentukan status Stream Sumber (render/upload tidak).
PIPELINE_TYPES = {"download", "record_live", "transcribe", "detect_layout", "score_highlights"}


class JobInfo(Protocol):
    id: int
    job_type: str
    source_stream_id: int | None
    scope_start_ms: int | None


def set_stream_status(conn: Connection, stream_id: int, new: str,
                      error: str | None = None) -> bool:
    """Ubah status Stream Sumber hanya jika transisinya sah menurut state machine."""
    current = conn.execute(text("SELECT status FROM source_streams WHERE id = :id"),
                           {"id": stream_id}).scalar()
    if current is None or new not in STREAM_TRANSITIONS.get(current, set()):
        if current != new:
            log.warning("transisi stream dilewati", stream_id=stream_id, dari=current, ke=new)
        return False
    conn.execute(text("UPDATE source_streams SET status = :st, error_message = :err, "
                      "updated_at = :now WHERE id = :id"),
                 {"st": new, "err": error, "now": utcnow(), "id": stream_id})
    return True


def create_job(conn: Connection, job_type: str, stream_id: int, **cols: Any) -> int:
    cols = {"job_type": job_type, "source_stream_id": stream_id, **cols}
    names = ", ".join(cols)
    marks = ", ".join(f":{k}" for k in cols)
    return conn.execute(text(f"INSERT INTO jobs ({names}) VALUES ({marks}) RETURNING id"),
                        cols).scalar()


def _is_stream_wide(job: JobInfo) -> bool:
    return job.job_type in PIPELINE_TYPES and job.scope_start_ms is None


def _latest_succeeded(conn: Connection, stream_id: int, job_type: str) -> bool:
    status = conn.execute(text(
        "SELECT status FROM jobs WHERE source_stream_id = :s AND job_type = :t "
        "AND scope_start_ms IS NULL ORDER BY id DESC LIMIT 1"),
        {"s": stream_id, "t": job_type}).scalar()
    return status == "succeeded"


def on_start(conn: Connection, job: JobInfo) -> None:
    if job.job_type == "download":
        set_stream_status(conn, job.source_stream_id, "downloading")


def on_success(conn: Connection, job: JobInfo) -> None:
    if not _is_stream_wide(job):
        # shortcut: transcribe berrentang (Penanda Live) tidak memicu Job lain; blok analisis
        # live (FR-013) membuat score_highlights per blok di v1.1. render/upload: T-046 & v1.1.
        return
    stream = job.source_stream_id
    if job.job_type in ("download", "record_live"):
        set_stream_status(conn, stream, "processing")
        create_job(conn, "detect_layout", stream)
        duration = conn.execute(text("SELECT duration_ms FROM source_streams WHERE id = :s"),
                                {"s": stream}).scalar()
        create_job(conn, "transcribe", stream,
                   awaiting_confirmation=int(usage.needs_confirmation(conn, duration)))
    elif job.job_type == "transcribe":
        create_job(conn, "score_highlights", stream)
    if job.job_type in ("detect_layout", "score_highlights") and all(
            _latest_succeeded(conn, stream, t) for t in ("detect_layout", "score_highlights")):
        set_stream_status(conn, stream, "ready")


def on_failed(conn: Connection, job: JobInfo, error: str | None) -> None:
    if _is_stream_wide(job) and job.source_stream_id is not None:
        set_stream_status(conn, job.source_stream_id, "failed", error)
