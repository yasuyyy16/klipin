"""T-017: SSE GET /events. TC-047."""

import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn
from sqlalchemy import text

from klipin.api.app import create_app
from klipin.api.deps import get_db_engine
from klipin.api.routes import events
from klipin.api.routes.events import ChangeTracker
from tests.conftest import TOKEN


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title) "
            "VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream uji')")
    return engine


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def exec_sql(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def test_tracker_emits_only_changes_after_connect(db):
    exec_sql(db, "INSERT INTO jobs (id, job_type, source_stream_id, updated_at) "
                 "VALUES (1, 'download', 1, '2026-01-01T00:00:00Z')")  # lama: tidak dikirim
    now = datetime.now(UTC)
    tracker = ChangeTracker(now - timedelta(seconds=1))
    with db.connect() as conn:
        assert [e for e, _ in tracker.poll(conn, now)] == ["stream.updated"]  # dibuat barusan
        assert tracker.poll(conn, now) == []

    exec_sql(db, "INSERT INTO jobs (id, job_type, source_stream_id, updated_at) "
                 "VALUES (2, 'download', 1, :t)", t=iso(now))
    with db.connect() as conn:
        (event, data), = tracker.poll(conn, now)
    assert event == "job.updated"
    assert data == {"id": 2, "job_type": "download", "status": "queued", "progress_pct": 0,
                    "stage": None, "source_stream_id": 1, "clip_id": None,
                    "awaiting_confirmation": False, "error_message": None}

    # perubahan kedua di detik yang sama tetap terdeteksi
    exec_sql(db, "UPDATE jobs SET progress_pct = 40, stage = 'x' WHERE id = 2")
    with db.connect() as conn:
        (event, data), = tracker.poll(conn, now)
    assert (event, data["progress_pct"]) == ("job.updated", 40)


def test_tracker_clip_created_then_updated_and_counts(db):
    now = datetime.now(UTC)
    tracker = ChangeTracker(now - timedelta(seconds=1))
    with db.connect() as conn:
        tracker.poll(conn, now)
    exec_sql(db, "INSERT INTO clips (id, source_stream_id, origin, start_ms, end_ms, "
                 "layout_preset_id, subtitle_style_id) VALUES (7, 1, 'auto', 0, 30000, 1, 1)")
    exec_sql(db, "UPDATE source_streams SET status = 'downloading', updated_at = :t", t=iso(now))
    with db.connect() as conn:
        got = dict(tracker.poll(conn, now))
    assert got["clip.created"] == {"id": 7, "source_stream_id": 1, "origin": "auto",
                                   "status": "candidate"}
    assert got["stream.updated"]["clip_counts"] == {"candidate": 1}
    exec_sql(db, "UPDATE clips SET status = 'approved' WHERE id = 7")
    with db.connect() as conn:
        assert [e for e, _ in tracker.poll(conn, now)] == ["clip.updated"]


def test_sixth_connection_rejected(api, monkeypatch):
    monkeypatch.setattr(events, "_connections", events.MAX_CONNECTIONS)
    resp = api.get(f"/api/v1/events?t={TOKEN}")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "TOO_MANY_CONNECTIONS"


@pytest.fixture
def live_server(db, home, tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    dist = tmp_path / "dist"
    dist.mkdir()
    app = create_app(token=TOKEN, dist_dir=dist, port=port)
    app.dependency_overrides[get_db_engine] = lambda: db
    server = uvicorn.Server(uvicorn.Config(app, log_config=None))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(5)


def test_tc047_job_update_arrives_within_3s(db, live_server):
    port = live_server
    exec_sql(db, "INSERT INTO jobs (id, job_type, source_stream_id) VALUES (5, 'download', 1)")
    received: list[tuple[float, dict]] = []
    ready = threading.Event()

    def listen():
        url = f"http://127.0.0.1:{port}/api/v1/events?t={TOKEN}"
        with httpx.stream("GET", url, timeout=10) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            event = None
            for line in resp.iter_lines():
                ready.set()
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event == "job.updated":
                    data = json.loads(line[6:])
                    if data["progress_pct"] == 55:
                        received.append((time.monotonic(), data))
                        return

    listener = threading.Thread(target=listen, daemon=True)
    listener.start()
    assert ready.wait(5)
    changed_at = time.monotonic()
    exec_sql(db, "UPDATE jobs SET status = 'running', progress_pct = 55, updated_at = :t "
                 "WHERE id = 5", t=iso(datetime.now(UTC)))
    listener.join(5)
    assert received, "event job.updated tidak diterima"
    arrived, data = received[0]
    assert arrived - changed_at <= 3
    assert (data["id"], data["status"]) == (5, "running")
