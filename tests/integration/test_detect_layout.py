"""T-031: handler Job `detect_layout` dengan MediaPipe/YuNet asli + fixture video. TC-015, TC-016."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from klipin.layout import regions
from klipin.layout.face_detect import FaceDetector
from klipin.worker.handlers import detect_layout
from klipin.worker.loop import claim, run_job
from klipin.worker.pipeline import create_job

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def setup_stream(engine, video, channel_id=None, duration_ms=30_000):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO source_streams (id, channel_id, source_type, platform, title, status, "
            "video_path, duration_ms) VALUES (1, :c, 'local_file', 'local', 'Uji layout', "
            "'processing', :v, :d)"),
            {"c": channel_id, "v": str(FIXTURES / video), "d": duration_ms})
        return create_job(conn, "detect_layout", 1)


def run(engine):
    ctx = claim(engine, heavy=True)
    run_job(ctx)
    return q(engine, "SELECT status, error_message, log_tail FROM jobs WHERE id = :i", i=ctx.id)[0]


def suggested(engine):
    return q(engine, "SELECT p.code FROM source_streams s LEFT JOIN layout_presets p "
                     "ON p.id = s.suggested_layout_preset_id")[0][0]


def stream_regions(engine):
    return {r.role: regions.Region(r.role, r.x, r.y, r.w, r.h, r.confidence) for r in q(
        engine, "SELECT role, x, y, w, h, confidence FROM cam_regions WHERE source_stream_id = 1")}


def test_tc015_gaming_facecam(engine, home):
    setup_stream(engine, "gaming_facecam_30s.mp4")
    status, error, log = run(engine)
    assert (status, error) == ("succeeded", None)
    assert suggested(engine) == "gaming"
    found = stream_regions(engine)
    truth = json.loads((FIXTURES / "gaming_facecam_30s.regions.json").read_text())["regions"][0]
    gt = regions.Region("cam", truth["x"], truth["y"], truth["w"], truth["h"], None)
    assert regions.iou(found["cam"], gt) >= 0.8
    assert 0 < found["cam"].confidence <= 1
    content = found["content"]
    assert (content.x, content.y, content.h) == (0.0, 0.0, 1.0)
    assert content.w == pytest.approx(found["cam"].x)  # konten = sisi kiri kolom cam
    assert "saran preset: gaming" in log


def test_tc016_no_face(engine, home):
    setup_stream(engine, "no_face_30s.mp4")
    status, _, log = run(engine)
    assert status == "succeeded"
    assert suggested(engine) == "center_crop"
    assert stream_regions(engine) == {}
    assert "Wajah tidak terdeteksi. Tandai area kamera manual jika ada." in log


def test_podcast_two_faces(engine, home):
    setup_stream(engine, "podcast_two_faces_30s.mp4")
    assert run(engine)[0] == "succeeded"
    assert suggested(engine) == "podcast"
    found = stream_regions(engine)
    assert set(found) == {"face_a", "face_b"}
    assert found["face_a"].x + found["face_a"].w <= 0.55 < found["face_b"].x + 0.1
    assert found["face_b"].x >= 0.45


def test_irl_moving_face(engine, home):
    setup_stream(engine, "irl_moving_face_30s.mp4")
    assert run(engine)[0] == "succeeded"
    assert suggested(engine) == "irl"
    assert stream_regions(engine) == {}


def test_channel_default_wins_and_is_verified(engine, home):
    with engine.begin() as conn:
        gaming = conn.execute(text("SELECT id FROM layout_presets WHERE code = 'gaming'")).scalar()
        conn.execute(text("INSERT INTO channels (id, platform, external_id, name, "
                          "default_layout_preset_id) VALUES (4, 'youtube', 'UC1', 'Kanal', :p)"),
                     {"p": gaming})
        conn.execute(text("INSERT INTO cam_regions (channel_id, role, x, y, w, h) "
                          "VALUES (4, 'cam', 0.65, 0.525926, 0.333333, 0.444444)"))
    setup_stream(engine, "gaming_facecam_30s.mp4", channel_id=4)
    status, _, log = run(engine)
    assert status == "succeeded"
    assert suggested(engine) == "gaming"
    assert "Preset default Kanal dipakai: gaming (deteksi: gaming)" in log
    assert "Region cam Kanal vs deteksi: IoU" in log and "(cocok)" in log
    # region Kanal tidak diubah oleh deteksi
    assert q(engine, "SELECT count(*) FROM cam_regions WHERE channel_id = 4") == [(1,)]


def test_channel_default_used_even_without_faces(engine, home):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO channels (id, platform, external_id, name, "
                          "default_layout_preset_id) SELECT 4, 'youtube', 'UC1', 'Kanal', id "
                          "FROM layout_presets WHERE code = 'gaming'"))
    setup_stream(engine, "no_face_30s.mp4", channel_id=4)
    assert run(engine)[0] == "succeeded"
    assert suggested(engine) == "gaming"


def test_corrupt_video_fails(engine, home):
    setup_stream(engine, "corrupt.mp4", duration_ms=None)
    status, error, _ = run(engine)
    assert (status, error) == ("failed", detect_layout.MSG_UNREADABLE)


def test_missing_video_fails(engine, home):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO source_streams (id, source_type, platform, source_url, "
                          "title, status) VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', "
                          "'Tanpa video', 'processing')"))
        create_job(conn, "detect_layout", 1)
    assert run(engine)[:2] == ("failed", detect_layout.MSG_NO_SOURCE)


def test_resume_from_checkpoint_skips_detection(engine, home, monkeypatch):
    setup_stream(engine, "no_face_30s.mp4")
    faces = {str(t): [] for t in detect_layout.sample_times(30_000)}
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET checkpoint = :c"), {"c": json.dumps({"faces": faces})})

    def never():
        raise AssertionError("detektor tidak boleh dibuat: semua sampel sudah ada di checkpoint")

    monkeypatch.setattr(detect_layout, "FaceDetector", never)
    ctx = claim(engine, heavy=True)
    detect_layout.run(ctx, detector_factory=never)
    assert suggested(engine) == "center_crop"


def test_yunet_fallback_alone_finds_facecam(engine, home):
    setup_stream(engine, "gaming_facecam_30s.mp4")

    def yunet_only():
        d = FaceDetector()
        d.primary = None
        return d

    ctx = claim(engine, heavy=True)
    found = detect_layout.run(ctx, detector_factory=yunet_only)
    assert found.preset == "gaming"


def test_sample_times():
    assert len(detect_layout.sample_times(30_000)) == 10  # minimal 10 untuk video pendek
    assert len(detect_layout.sample_times(3_600_000)) == 360  # 1 per 10 detik
    times = detect_layout.sample_times(3 * 3_600_000)
    assert len(times) == 600 and times[0] > 0 and times[-1] < 3 * 3_600_000
