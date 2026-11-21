"""T-030: konfirmasi perkiraan pemakaian (FR-022). TC-043, TC-044."""

from pathlib import Path

import pytest
from sqlalchemy import text

from klipin import secrets, usage
from klipin.providers.transcriber import FakeTranscriber
from klipin.worker.handlers import HANDLERS, transcribe
from klipin.worker.loop import claim, run_job
from klipin.worker.pipeline import create_job

AUDIO_25MIN = Path(__file__).resolve().parents[1] / "fixtures" / "audio_25min_scream_at_10.flac"
MIN = 60_000


def setting(engine, key, value):
    with engine.begin() as conn:
        conn.execute(text("UPDATE settings SET value = :v WHERE key = :k"), {"v": value, "k": key})


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


@pytest.fixture
def db(engine, home, monkeypatch):
    monkeypatch.setitem(HANDLERS, "download", lambda ctx: None)  # video dianggap sudah ada
    return engine


def import_stream(engine, duration_ms, video=None):
    """Stream Sumber + Job download yang langsung sukses → pipeline membuat transcribe."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title, "
            "duration_ms, video_path) VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', "
            "'Stream panjang', :d, :v)"), {"d": duration_ms, "v": video})
        create_job(conn, "download", 1)
    run_job(claim(engine, heavy=True))
    return q(engine, "SELECT id, awaiting_confirmation FROM jobs WHERE job_type = 'transcribe'")[0]


def test_tc043_long_stream_waits_for_confirmation(api, db):
    job_id, held = import_stream(db, 130 * MIN)  # 2 jam 10 menit
    assert held == 1
    # Worker tidak mengambil transcribe yang ditahan; detect_layout tetap jalan
    assert claim(db, heavy=True).job_type == "detect_layout"
    assert claim(db, heavy=True) is None

    detail = api.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["usage_estimate"] == {
        "audio_ms": 7_800_000, "estimated_llm_windows": 260, "duration_ms": 7_800_000,
        "max_audio_ms": 600 * MIN, "over_limit": False,
        "pricing_links": {"transcriber": "https://deepgram.com/pricing",
                          "llm": "https://claude.com/pricing#api"}}

    resp = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": False, "range": None})
    assert resp.status_code == 200 and resp.json()["awaiting_confirmation"] is True
    resp = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": True, "range": None})
    assert resp.status_code == 200 and resp.json()["awaiting_confirmation"] is False
    assert api.get(f"/api/v1/jobs/{job_id}").json()["usage_estimate"] is None
    assert claim(db, heavy=True).id == job_id


def test_short_stream_not_held(db):
    assert import_stream(db, 25 * MIN)[1] == 0


def test_threshold_zero_always(db):
    setting(db, "confirm_usage_over_min", "0")
    assert import_stream(db, 30_000)[1] == 1


def test_confirmation_off_with_null(db):
    setting(db, "confirm_usage_over_min", "null")
    assert import_stream(db, 300 * MIN)[1] == 0


def test_unknown_duration_not_held(db):
    assert import_stream(db, None)[1] == 0


def test_tc044_over_limit_needs_range(api, db, memory_keyring, monkeypatch):
    setting(db, "confirm_usage_over_min", "null")  # batas durasi tetap berlaku walau konfirmasi mati
    setting(db, "max_audio_minutes_per_job", "10")
    job_id, held = import_stream(db, 1_500_000, str(AUDIO_25MIN))
    assert held == 1
    est = api.get(f"/api/v1/jobs/{job_id}").json()["usage_estimate"]
    assert est["over_limit"] is True and est["max_audio_ms"] == 10 * MIN

    resp = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": True, "range": None})
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == (
        "Durasi audio 25 menit melebihi batas per Job (10 menit). Pilih rentang waktu tertentu "
        "atau naikkan batas di Pengaturan.")
    for bad, code in [({"start_ms": 0, "end_ms": 11 * MIN}, 400),
                      ({"start_ms": 20 * MIN, "end_ms": 26 * MIN}, 400),
                      ({"start_ms": 5 * MIN, "end_ms": 5 * MIN}, 400)]:
        r = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": True, "range": bad})
        assert r.status_code == code, bad
    assert api.post(f"/api/v1/jobs/{job_id}/confirm", json={
        "proceed": True, "range": {"start_ms": 0, "end_ms": 11 * MIN}}).json()["error"][
        "message"] == "Rentang melebihi batas durasi per Job (10 menit)."

    resp = api.post(f"/api/v1/jobs/{job_id}/confirm",
                    json={"proceed": True, "range": {"start_ms": 2 * MIN, "end_ms": 12 * MIN}})
    assert resp.status_code == 200 and resp.json()["awaiting_confirmation"] is False

    # Transkripsi hanya rentang itu, tetapi tetap dianggap Job seluruh stream (lanjut ke skor)
    secrets.set_secret("transcriber_api_key", "kunci-uji")
    fake = FakeTranscriber()
    monkeypatch.setattr(transcribe, "get_transcriber", lambda engine: fake)
    claim(db, heavy=True)  # detect_layout (tidak dijalankan di tes ini)
    ctx = claim(db, heavy=True)
    assert ctx.id == job_id
    run_job(ctx)
    assert q(db, "SELECT start_ms, end_ms FROM transcription_chunks") == [(2 * MIN, 12 * MIN)]
    lo, hi = q(db, "SELECT min(start_ms), max(end_ms) FROM transcript_words")[0]
    assert 2 * MIN <= lo and hi <= 12 * MIN
    assert q(db, "SELECT checkpoint FROM jobs WHERE id = :i", i=job_id)[0][0] == (
        '{"range": {"start_ms": 120000, "end_ms": 720000}, "chunks_done": 1, "chunks_total": 1}')
    assert ("score_highlights",) in q(db, "SELECT job_type FROM jobs")


def test_confirm_rejects_jobs_not_waiting(api, db):
    job_id, _ = import_stream(db, 5 * MIN)
    r = api.post(f"/api/v1/jobs/{job_id}/confirm", json={"proceed": True, "range": None})
    assert r.status_code == 409


def test_settings_confirm_threshold_nullable(api):
    r = api.patch("/api/v1/settings", json={"confirm_usage_over_min": None})
    assert r.status_code == 200 and r.json()["confirm_usage_over_min"] is None
    r = api.patch("/api/v1/settings", json={"confirm_usage_over_min": 45})
    assert r.json()["confirm_usage_over_min"] == 45
    assert api.patch("/api/v1/settings", json={"max_audio_minutes_per_job": None}
                     ).status_code == 400


@pytest.mark.parametrize(("ms", "text_"), [
    (130 * MIN, "2 jam 10 menit"), (45 * MIN, "45 menit"), (2 * 3_600_000, "2 jam"),
    (30_000, "30 detik")])
def test_format_duration(ms, text_):
    assert usage.format_duration(ms) == text_


def test_llm_window_estimate_follows_br003():
    assert usage.estimated_llm_windows(7_800_000) == 260
    assert usage.estimated_llm_windows(30_000) == 1
    assert usage.estimated_llm_windows(30_030) == 1
    assert usage.estimated_llm_windows(0) == 0
