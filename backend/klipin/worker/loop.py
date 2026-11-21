"""Worker: klaim Job atomik, batas paralel, heartbeat, pembatalan (04-arsitektur.md §3.1, ADR-002)."""

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import structlog
from sqlalchemy import Engine, text

from klipin.config import get_config
from klipin.db.backup import daily_backup
from klipin.db.models import JsonText, utcnow
from klipin.db.session import get_engine
from klipin.worker import pipeline
from klipin.worker.context import JobContext
from klipin.worker.handlers import get_handler
from klipin.worker.process import JobCancelled

log = structlog.get_logger(__name__)
HEARTBEAT_S = 10
STALE_S = 60
POLL_S = 1.0
BACKUP_CHECK_S = 60
INTERRUPTED = "Terhenti karena aplikasi ditutup"
NO_HANDLER = "Jenis Job ini belum didukung di versi ini."
_json = JsonText()

CLAIM_SQL = text("""
UPDATE jobs SET status = 'running', started_at = :now, worker_heartbeat_at = :now,
                updated_at = :now
WHERE id = (SELECT id FROM jobs
            WHERE status = 'queued' AND awaiting_confirmation = 0 AND is_heavy = :heavy
            ORDER BY priority DESC, created_at ASC, id ASC LIMIT 1)
  AND status = 'queued'
RETURNING id, job_type, source_stream_id, clip_id, upload_id, purpose, preview_at_ms,
          scope_start_ms, scope_end_ms, checkpoint
""")


JOB_INFO_COLS = "id, job_type, source_stream_id, scope_start_ms"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def mark_interrupted(engine: Engine, exclude: set[int] = frozenset(),
                     now: datetime | None = None) -> int:
    """Job `running` tanpa heartbeat > 60 detik → `failed` (FR-023, TC-046)."""
    now = now or datetime.now(UTC)
    cutoff = _iso(now - timedelta(seconds=STALE_S))
    ids = ",".join(str(i) for i in exclude) or "-1"
    with engine.begin() as conn:
        rows = conn.execute(text(
            "UPDATE jobs SET status = 'failed', error_message = :msg, finished_at = :now, "
            "updated_at = :now WHERE status = 'running' AND id NOT IN (" + ids + ") "
            "AND (worker_heartbeat_at IS NULL OR worker_heartbeat_at < :cutoff) "
            "RETURNING " + JOB_INFO_COLS),
            {"msg": INTERRUPTED, "now": _iso(now), "cutoff": cutoff}).mappings().all()
        for row in rows:
            pipeline.on_failed(conn, SimpleNamespace(**row), INTERRUPTED)
        return len(rows)


def claim(engine: Engine, heavy: bool) -> JobContext | None:
    with engine.begin() as conn:
        row = conn.execute(CLAIM_SQL, {"now": utcnow(), "heavy": int(heavy)}).mappings().first()
        if row is None:
            return None
        pipeline.on_start(conn, SimpleNamespace(**row))
    data = dict(row)
    data["checkpoint"] = _json.process_result_value(data["checkpoint"], None) or {}
    return JobContext(engine=engine, **data)


def max_heavy_jobs(engine: Engine) -> int:
    """Pengaturan `max_heavy_jobs` menang; env `KLIPIN_MAX_HEAVY_JOBS` hanya cadangan bila
    Pengaturan kosong (04-arsitektur.md §8.2, sama dengan pemilihan penyedia)."""
    with engine.connect() as conn:
        value = conn.execute(text("SELECT value FROM settings WHERE key = 'max_heavy_jobs'")
                             ).scalar()
    setting = _json.process_result_value(value, None) if value is not None else None
    return max(1, int(setting or get_config().klipin_max_heavy_jobs))


def _finish(engine: Engine, ctx: JobContext, status: str, error: str | None = None) -> None:
    now = utcnow()
    with engine.begin() as conn:
        if status == "cancelled":
            conn.execute(text("UPDATE jobs SET finished_at = COALESCE(finished_at, :now), "
                              "updated_at = :now WHERE id = :id AND status = 'cancelled'"),
                         {"now": now, "id": ctx.id})
            return
        result = conn.execute(text(
            "UPDATE jobs SET status = :st, error_message = :err, finished_at = :now, "
            "updated_at = :now, progress_pct = CASE WHEN :st = 'succeeded' THEN 100 "
            "ELSE progress_pct END WHERE id = :id AND status = 'running'"),
            {"st": status, "err": error, "now": now, "id": ctx.id})
        # Job berikutnya & status Stream Sumber ikut transaksi yang sama (§3.1).
        if result.rowcount and status == "succeeded":
            pipeline.on_success(conn, ctx)
        elif result.rowcount:
            pipeline.on_failed(conn, ctx, error)


def run_job(ctx: JobContext) -> None:
    """Jalankan handler di thread Worker dan tulis status akhirnya."""
    engine = ctx.engine
    handler = get_handler(ctx.job_type)
    try:
        if handler is None:
            raise RuntimeError(NO_HANDLER)
        handler(ctx)
        ctx.check_cancelled()
    except JobCancelled:
        log.info("job dibatalkan", job_id=ctx.id)
        _finish(engine, ctx, "cancelled")
    except Exception as exc:  # kegagalan handler apa pun = Job failed
        if ctx.cancel_event.is_set():  # error akibat proses dihentikan saat batal
            _finish(engine, ctx, "cancelled")
            return
        log.exception("job gagal", job_id=ctx.id, job_type=ctx.job_type)
        message = NO_HANDLER if handler is None else str(exc)[:500] or type(exc).__name__
        try:
            ctx.log(f"GAGAL: {message}")
        finally:
            _finish(engine, ctx, "failed", message)
    else:
        _finish(engine, ctx, "succeeded")


@dataclass
class Active:
    ctx: JobContext
    thread: threading.Thread
    heavy: bool


class Worker:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.active: dict[int, Active] = {}
        self.next_heartbeat = 0.0
        self.next_backup = 0.0

    def _start(self, ctx: JobContext, heavy: bool) -> None:
        thread = threading.Thread(target=run_job, args=(ctx,), name=f"job-{ctx.id}", daemon=True)
        self.active[ctx.id] = Active(ctx, thread, heavy)
        log.info("job mulai", job_id=ctx.id, job_type=ctx.job_type)
        thread.start()

    def _reap(self) -> None:
        for job_id in [i for i, a in self.active.items() if not a.thread.is_alive()]:
            del self.active[job_id]

    def _watch_cancel(self) -> None:
        if not self.active:
            return
        ids = ",".join(str(i) for i in self.active)
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT id, status FROM jobs WHERE id IN ({ids})")).all()
        for job_id, status in rows:
            if status != "running":
                self.active[job_id].ctx.cancel_event.set()

    def _heartbeat(self) -> None:
        if self.active:
            ids = ",".join(str(i) for i in self.active)
            with self.engine.begin() as conn:
                conn.execute(text(f"UPDATE jobs SET worker_heartbeat_at = :now WHERE id IN "
                                  f"({ids}) AND status = 'running'"), {"now": utcnow()})
        mark_interrupted(self.engine, exclude=set(self.active))

    def _claim_free_slots(self) -> None:
        heavy_free = max_heavy_jobs(self.engine) - sum(a.heavy for a in self.active.values())
        while heavy_free > 0 and (ctx := claim(self.engine, heavy=True)):
            self._start(ctx, heavy=True)
            heavy_free -= 1
        if not any(not a.heavy for a in self.active.values()) and (
                ctx := claim(self.engine, heavy=False)):
            self._start(ctx, heavy=False)

    def tick(self) -> None:
        self._reap()
        self._watch_cancel()
        if time.monotonic() >= self.next_heartbeat:
            self._heartbeat()
            self.next_heartbeat = time.monotonic() + HEARTBEAT_S
        self._claim_free_slots()

    def shutdown(self) -> None:
        """Hentikan handler yang berjalan; Job-nya ditandai seperti aplikasi ditutup."""
        for a in self.active.values():
            a.ctx.cancel_event.set()
        ids = list(self.active)
        if ids:
            with self.engine.begin() as conn:
                rows = conn.execute(text(
                    f"UPDATE jobs SET status = 'failed', error_message = :msg, "
                    f"finished_at = :now, updated_at = :now "
                    f"WHERE id IN ({','.join(map(str, ids))}) AND status = 'running' "
                    f"RETURNING {JOB_INFO_COLS}"),
                    {"msg": INTERRUPTED, "now": utcnow()}).mappings().all()
                for row in rows:
                    pipeline.on_failed(conn, SimpleNamespace(**row), INTERRUPTED)
        for a in self.active.values():
            a.thread.join(timeout=10)


def run() -> int:
    engine = get_engine()
    home = get_config().klipin_home
    count = mark_interrupted(engine)
    if count:
        log.warning("job terputus ditandai gagal", count=count)
    worker = Worker(engine)
    log.info("worker berjalan")
    try:
        while True:
            worker.tick()
            if time.monotonic() >= worker.next_backup:
                try:
                    daily_backup(home)
                except (OSError, sqlite3.Error):
                    log.exception("backup harian gagal")
                worker.next_backup = time.monotonic() + BACKUP_CHECK_S
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        worker.shutdown()
        return 0
