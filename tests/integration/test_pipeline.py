"""T-015: orkestrator pipeline + status Stream Sumber, dengan handler palsu."""

import time

import pytest
from sqlalchemy import text

from klipin import secrets
from klipin.worker import pipeline
from klipin.worker.context import JobContext
from klipin.worker.handlers import HANDLERS, fake
from klipin.worker.loop import Worker, claim, mark_interrupted


@pytest.fixture
def db(engine, home, memory_keyring, monkeypatch):
    monkeypatch.setattr(fake, "STEP_S", 0.0)
    secrets.set_secret("transcriber_api_key", "kunci-uji")  # transcribe asli + FakeTranscriber
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title) "
            "VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream uji')")
        pipeline.create_job(conn, "download", 1)
    return engine


def stream_status(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT status, error_message FROM source_streams WHERE id = 1")
                            ).one()


def jobs(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT job_type, status FROM jobs ORDER BY id")).all()


def run_until_idle(engine, timeout=15.0):
    worker = Worker(engine)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        worker.tick()
        with engine.connect() as conn:
            busy = conn.execute(text(
                "SELECT count(*) FROM jobs WHERE status IN ('queued', 'running')")).scalar()
        if not busy and not worker.active:
            return
        time.sleep(0.01)
    raise AssertionError("pipeline tidak selesai")


def test_download_start_sets_downloading(db):
    assert claim(db, heavy=True).job_type == "download"
    assert stream_status(db)[0] == "downloading"


def test_vod_chain_to_ready(db):
    run_until_idle(db)
    assert jobs(db) == [
        ("download", "succeeded"),
        ("detect_layout", "succeeded"),
        ("transcribe", "succeeded"),
        ("score_highlights", "succeeded"),
    ]
    assert stream_status(db) == ("ready", None)


def test_transcribe_failure_fails_stream(db, monkeypatch):
    def broken(ctx: JobContext) -> None:
        raise RuntimeError("API transkripsi menolak audio")

    monkeypatch.setitem(HANDLERS, "transcribe", broken)  # pulih otomatis; jangan hapus handler asli
    run_until_idle(db)
    assert ("score_highlights", "succeeded") not in jobs(db)
    assert ("transcribe", "failed") in jobs(db)
    assert stream_status(db) == ("failed", "API transkripsi menolak audio")


def test_ready_needs_both_layout_and_scores(db, monkeypatch):
    def broken(ctx: JobContext) -> None:
        raise RuntimeError("deteksi gagal")

    monkeypatch.setitem(HANDLERS, "detect_layout", broken)  # pulih otomatis; jangan hapus handler asli
    run_until_idle(db)
    assert ("score_highlights", "succeeded") in jobs(db)
    assert stream_status(db)[0] == "failed"


def test_scoped_transcribe_does_not_touch_stream(db, monkeypatch):
    # Orkestrasi saja: handler palsu (transkripsi berrentang asli diuji di T-027).
    monkeypatch.delitem(HANDLERS, "transcribe")
    with db.begin() as conn:
        conn.execute(text("DELETE FROM jobs"))
        conn.execute(text("UPDATE source_streams SET status = 'ready'"))
        pipeline.create_job(conn, "transcribe", 1, scope_start_ms=0, scope_end_ms=60_000,
                            is_heavy=0)
    run_until_idle(db)
    assert jobs(db) == [("transcribe", "succeeded")]
    assert stream_status(db)[0] == "ready"


def test_invalid_transition_is_skipped(db):
    with db.begin() as conn:
        assert pipeline.set_stream_status(conn, 1, "ready") is False  # queued -> ready tidak sah
        assert pipeline.set_stream_status(conn, 1, "downloading") is True
    assert stream_status(db)[0] == "downloading"


def test_interrupted_download_fails_stream(db):
    with db.begin() as conn:
        conn.execute(text("UPDATE jobs SET status = 'running', worker_heartbeat_at = NULL"))
        conn.execute(text("UPDATE source_streams SET status = 'downloading'"))
    assert mark_interrupted(db) == 1
    assert stream_status(db) == ("failed", "Terhenti karena aplikasi ditutup")
