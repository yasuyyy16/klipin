"""T-014: Worker loop (klaim atomik, slot, heartbeat, batal, checkpoint, log_tail). TC-046."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from klipin.config import get_config
from klipin.worker import loop
from klipin.worker.context import LOG_TAIL_MAX, JobContext
from klipin.worker.handlers import HANDLERS, fake
from klipin.worker.loop import INTERRUPTED, NO_HANDLER, Worker, claim, mark_interrupted

# Job dummy = detect_layout tanpa handler asli (dipulihkan otomatis oleh monkeypatch): di mode
# fake memakai handler palsu bertahap, di mode real gagal "tidak ada handler".
DUMMY = "detect_layout"
# Proses Worker terpisah untuk TC-046 dengan perlakuan yang sama.
WORKER_WITH_DUMMY = ("import sys; from klipin.worker.handlers import HANDLERS; "
                     f"HANDLERS.pop({DUMMY!r}); from klipin.__main__ import main; "
                     "sys.argv = ['klipin', 'worker']; main()")


@pytest.fixture
def db(engine, home, monkeypatch):
    monkeypatch.setattr(fake, "STEP_S", 0.02)
    monkeypatch.delitem(HANDLERS, DUMMY)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title) "
            "VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream uji')")
    return engine


def add_job(engine, job_type=DUMMY, **cols):
    cols = {"job_type": job_type, "source_stream_id": 1, **cols}
    names = ", ".join(cols)
    marks = ", ".join(f":{k}" for k in cols)
    with engine.begin() as conn:
        return conn.execute(text(f"INSERT INTO jobs ({names}) VALUES ({marks}) RETURNING id"),
                            cols).scalar()


def job(engine, job_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}
                            ).mappings().one()


def drive(worker, until, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        worker.tick()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("kondisi tidak tercapai sebelum timeout")


def iso_ago(seconds):
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_claim_order_and_filters(db):
    low = add_job(db, priority=0)
    high = add_job(db, priority=5)
    add_job(db, awaiting_confirmation=1, priority=99)  # menunggu konfirmasi: dilewati
    light = add_job(db, "transcribe", is_heavy=0, scope_start_ms=0, scope_end_ms=60000)
    assert claim(db, heavy=True).id == high
    assert claim(db, heavy=True).id == low
    assert claim(db, heavy=True) is None
    assert claim(db, heavy=False).id == light
    assert job(db, high)["status"] == "running"


def test_dummy_job_runs_to_success(db):
    job_id = add_job(db)
    worker = Worker(db)
    drive(worker, lambda: job(db, job_id)["status"] == "succeeded")
    row = job(db, job_id)
    assert row["progress_pct"] == 100
    assert json.loads(row["checkpoint"]) == {"steps_done": fake.STEPS}
    assert row["started_at"] and row["finished_at"] and row["worker_heartbeat_at"]


def test_cancel_running_job(db, monkeypatch):
    monkeypatch.setattr(fake, "STEP_S", 0.2)
    job_id = add_job(db)
    worker = Worker(db)
    drive(worker, lambda: job(db, job_id)["progress_pct"] > 0)
    with db.begin() as conn:  # yang dilakukan POST /jobs/{id}/cancel (T-016)
        conn.execute(text("UPDATE jobs SET status = 'cancelled' WHERE id = :id"), {"id": job_id})
    start = time.monotonic()
    drive(worker, lambda: not worker.active)
    assert time.monotonic() - start < 10
    row = job(db, job_id)
    assert row["status"] == "cancelled"
    assert row["finished_at"]
    assert json.loads(row["checkpoint"])["steps_done"] < fake.STEPS


def test_cancel_kills_subprocess_within_10s(db, monkeypatch):
    def sleeper(ctx: JobContext) -> None:
        ctx.run([sys.executable, "-c", "import time; time.sleep(60)"])

    monkeypatch.setitem(HANDLERS, "render", sleeper)
    with db.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, "
            "layout_preset_id, subtitle_style_id) VALUES (1, 1, 'auto', 'approved', 0, "
            "30000, 1, 1)")
    job_id = add_job(db, "render", clip_id=1)
    worker = Worker(db)
    drive(worker, lambda: job(db, job_id)["status"] == "running")
    time.sleep(0.5)
    with db.begin() as conn:
        conn.execute(text("UPDATE jobs SET status = 'cancelled' WHERE id = :id"),
                     {"id": job_id})
    start = time.monotonic()
    drive(worker, lambda: not worker.active, timeout=12)
    assert time.monotonic() - start <= 10
    assert job(db, job_id)["status"] == "cancelled"


def test_heavy_slots_and_light_slot(db, monkeypatch):
    monkeypatch.setattr(fake, "STEP_S", 0.2)
    heavy = [add_job(db) for _ in range(3)]
    light = add_job(db, "transcribe", is_heavy=0, scope_start_ms=0, scope_end_ms=60000)
    worker = Worker(db)
    worker.tick()
    assert set(worker.active) == {heavy[0], light}  # max_heavy_jobs=1 + 1 slot ringan

    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE settings SET value = '2' WHERE key = 'max_heavy_jobs'")
    worker.tick()
    assert set(worker.active) == {heavy[0], heavy[1], light}
    worker.shutdown()


def test_env_max_heavy_jobs_overrides_settings(db, monkeypatch):
    monkeypatch.setenv("KLIPIN_MAX_HEAVY_JOBS", "3")
    get_config.cache_clear()
    assert loop.max_heavy_jobs(db) == 3


def test_mark_interrupted_only_stale_jobs(db):
    stale = add_job(db, status="running", worker_heartbeat_at=iso_ago(120))
    fresh = add_job(db, status="running", worker_heartbeat_at=iso_ago(5))
    assert mark_interrupted(db) == 1
    assert job(db, stale)["status"] == "failed"
    assert job(db, stale)["error_message"] == INTERRUPTED
    assert job(db, fresh)["status"] == "running"


def test_unknown_job_type_fails_without_fake(db, monkeypatch):
    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    job_id = add_job(db, DUMMY)
    drive(Worker(db), lambda: job(db, job_id)["status"] == "failed")
    assert job(db, job_id)["error_message"] == NO_HANDLER


def test_handler_exception_marks_failed_with_log(db, monkeypatch):
    def broken(ctx: JobContext) -> None:
        ctx.log("mulai")
        raise ValueError("format audio tidak dikenali")

    monkeypatch.setitem(HANDLERS, "transcribe", broken)
    job_id = add_job(db, "transcribe")
    drive(Worker(db), lambda: job(db, job_id)["status"] == "failed")
    row = job(db, job_id)
    assert row["error_message"] == "format audio tidak dikenali"
    assert row["log_tail"] == "mulai\nGAGAL: format audio tidak dikenali\n"


def test_log_tail_is_capped(db):
    job_id = add_job(db, status="running")
    ctx = JobContext(engine=db, id=job_id, job_type="download", source_stream_id=1,
                     clip_id=None, upload_id=None, purpose="final", preview_at_ms=None,
                     scope_start_ms=None, scope_end_ms=None, checkpoint={})
    for i in range(300):
        ctx.log(f"baris log nomor {i:04d} " + "x" * 20)
    tail = job(db, job_id)["log_tail"]
    assert len(tail) <= LOG_TAIL_MAX
    assert tail.endswith("baris log nomor 0299 " + "x" * 20 + "\n")


def test_tc046_kill_worker_then_restart(db, home):
    """Kill proses Worker saat Job dummy jalan; start ulang → failed + DB utuh + lanjut."""
    job_id = add_job(db)
    env = {**os.environ, "KLIPIN_HOME": str(home), "KLIPIN_PROVIDERS": "fake"}
    proc = subprocess.Popen([sys.executable, "-c", WORKER_WITH_DUMMY], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.monotonic() + 30
        while job(db, job_id)["progress_pct"] < 15:
            assert time.monotonic() < end, "worker tidak memulai Job"
            time.sleep(0.2)
    finally:
        proc.kill()  # tutup paksa, tanpa kesempatan membereskan
        proc.wait(10)
    assert job(db, job_id)["status"] == "running"

    with db.begin() as conn:  # majukan jam: heartbeat terakhir sudah > 60 detik lalu
        conn.execute(text("UPDATE jobs SET worker_heartbeat_at = :t WHERE id = :id"),
                     {"t": iso_ago(90), "id": job_id})
    assert mark_interrupted(db) == 1  # yang dijalankan Worker saat start
    row = job(db, job_id)
    assert (row["status"], row["error_message"]) == ("failed", INTERRUPTED)
    done = json.loads(row["checkpoint"])["steps_done"]
    assert 0 < done < fake.STEPS

    with sqlite3.connect(home / "klipin.db") as raw:
        assert raw.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    raw.close()

    # Coba ulang (T-016 membuat Job baru + menyalin checkpoint): melanjutkan, bukan dari nol.
    retry = add_job(db, retry_of_job_id=job_id, checkpoint=row["checkpoint"])
    drive(Worker(db), lambda: job(db, retry)["status"] == "succeeded")
    assert f"lanjut dari langkah {done + 1}/{fake.STEPS}" in job(db, retry)["log_tail"]
