"""T-016: API Job (list, detail, cancel, retry, confirm). TC-045 dengan Job dummy."""

import json
import sys
import time

import pytest
from sqlalchemy import text

from klipin.worker.context import JobContext
from klipin.worker.handlers import HANDLERS
from klipin.worker.loop import Worker


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title, status) "
            "VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream uji', 'processing')")
        conn.exec_driver_sql(
            "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, "
            "layout_preset_id, subtitle_style_id) VALUES (1, 1, 'auto', 'approved', 0, 30000, 1, 1)")
    return engine


def add_job(engine, job_type="transcribe", **cols):
    cols = {"job_type": job_type, "source_stream_id": 1, **cols}
    with engine.begin() as conn:
        return conn.execute(text(
            f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)}) "
            "RETURNING id"), cols).scalar()


def one(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).one()


def test_list_filters_and_paginates(api, db):
    a = add_job(db, status="queued")
    b = add_job(db, status="running")
    add_job(db, status="succeeded")
    body = api.get("/api/v1/jobs", params={"status": "queued,running"}).json()
    assert body["total"] == 2
    assert [j["id"] for j in body["items"]] == [b, a]  # terbaru dulu
    assert body["items"][0]["awaiting_confirmation"] is False
    assert body["items"][0]["stream_title"] == "Stream uji"
    page = api.get("/api/v1/jobs", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert api.get("/api/v1/jobs", params={"source_stream_id": 99}).json()["total"] == 0


@pytest.mark.parametrize("params", [{"status": "paused"}, {"limit": 201}, {"offset": -1}])
def test_list_rejects_bad_params(api, db, params):
    assert api.get("/api/v1/jobs", params=params).status_code == 400


def test_detail_has_log_tail_and_404(api, db):
    job_id = add_job(db, log_tail="baris 1\n")
    assert api.get(f"/api/v1/jobs/{job_id}").json()["log_tail"] == "baris 1\n"
    resp = api.get("/api/v1/jobs/999")
    assert resp.status_code == 404
    assert resp.json()["error"] == {"code": "NOT_FOUND", "message": "Job tidak ditemukan."}


def test_cancel_queued_and_finished(api, db):
    job_id = add_job(db)
    resp = api.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["finished_at"]
    again = api.post(f"/api/v1/jobs/{job_id}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_STATE"


def test_cancel_pipeline_job_fails_stream(api, db):
    job_id = add_job(db)
    api.post(f"/api/v1/jobs/{job_id}/cancel")
    assert one(db, "SELECT status, error_message FROM source_streams WHERE id = 1") == (
        "failed", "Job dibatalkan.")


def test_tc045_cancel_running_render(api, db, monkeypatch):
    def slow_render(ctx: JobContext) -> None:
        ctx.run([sys.executable, "-c", "import time; time.sleep(60)"])

    monkeypatch.setitem(HANDLERS, "render", slow_render)
    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE clips SET status = 'rendering' WHERE id = 1")
    job_id = add_job(db, "render", clip_id=1)
    worker = Worker(db)
    worker.tick()
    time.sleep(0.5)  # subprocess sudah berjalan
    assert api.post(f"/api/v1/jobs/{job_id}/cancel").json()["status"] == "cancelled"
    start = time.monotonic()
    while worker.active and time.monotonic() - start < 12:
        worker.tick()
        time.sleep(0.05)
    assert not worker.active
    assert time.monotonic() - start <= 10
    assert one(db, "SELECT status FROM jobs WHERE id = :id", id=job_id) == ("cancelled",)
    assert one(db, "SELECT status FROM clips WHERE id = 1") == ("approved",)


def test_retry_copies_checkpoint(api, db):
    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE source_streams SET status = 'failed' WHERE id = 1")
    old = add_job(db, status="failed", checkpoint=json.dumps({"chunks_done": [0, 1, 2]}),
                  priority=3)
    resp = api.post(f"/api/v1/jobs/{old}/retry")
    assert resp.status_code == 202
    new = resp.json()["job"]
    assert (new["retry_of_job_id"], new["status"], new["priority"]) == (old, "queued", 3)
    row = one(db, "SELECT checkpoint FROM jobs WHERE id = :id", id=new["id"])
    assert json.loads(row[0]) == {"chunks_done": [0, 1, 2]}
    assert one(db, "SELECT status FROM source_streams WHERE id = 1") == ("processing",)
    assert api.post(f"/api/v1/jobs/{old}/retry").status_code == 409  # sudah dicoba ulang


def test_retry_download_requeues_stream(api, db):
    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE source_streams SET status = 'failed' WHERE id = 1")
    old = add_job(db, "download", status="failed")
    assert api.post(f"/api/v1/jobs/{old}/retry").status_code == 202
    assert one(db, "SELECT status FROM source_streams WHERE id = 1") == ("queued",)


def test_retry_failed_render_moves_clip_back_to_rendering(api, db):
    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE clips SET status = 'render_failed' WHERE id = 1")
    old = add_job(db, "render", clip_id=1, status="failed")
    assert api.post(f"/api/v1/jobs/{old}/retry").status_code == 202
    assert one(db, "SELECT status FROM clips WHERE id = 1") == ("rendering",)


@pytest.mark.parametrize("status", ["queued", "running", "succeeded"])
def test_retry_only_failed_or_cancelled(api, db, status):
    job_id = add_job(db, status=status)
    assert api.post(f"/api/v1/jobs/{job_id}/retry").json()["error"]["code"] == "INVALID_STATE"


def test_retry_when_source_deleted(api, db):
    with db.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE source_streams SET source_deleted_at = '2026-11-20T00:00:00Z' WHERE id = 1")
    job_id = add_job(db, status="failed")
    resp = api.post(f"/api/v1/jobs/{job_id}/retry")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SOURCE_DELETED"


def test_confirm(api, db):
    job_id = add_job(db, awaiting_confirmation=1)
    held = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": False})
    assert held.json()["awaiting_confirmation"] is True
    ok = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": True, "range": None})
    assert ok.status_code == 200
    assert ok.json()["awaiting_confirmation"] is False
    assert api.post(f"/api/v1/jobs/{job_id}/confirm",
                    json={"proceed": True}).status_code == 409
