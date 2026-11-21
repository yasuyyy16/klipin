"""T-034: layout-presets, channels, regions stream/klip, frame JPEG. TC-017."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from sqlalchemy import text

from klipin import layouts
from tests.conftest import PORT, TOKEN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GAMING = FIXTURES / "gaming_facecam_30s.mp4"
CAM = {"role": "cam", "x": 0.65, "y": 0.525926, "w": 0.333333, "h": 0.444444}
CONTENT = {"role": "content", "x": 0.0, "y": 0.0, "w": 0.65, "h": 1.0}


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def preset_id(engine, code):
    return q(engine, "SELECT id FROM layout_presets WHERE code = :c", c=code)[0][0]


@pytest.fixture
def db(engine):
    gaming = preset_id(engine, "gaming")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO channels (id, platform, external_id, name) "
                          "VALUES (4, 'youtube', 'UC1', 'Kanal Gaming')"))
        conn.execute(text(
            "INSERT INTO source_streams (id, channel_id, source_type, platform, source_url, title, "
            "status, video_path, duration_ms) VALUES "
            "(1, 4, 'vod_url', 'youtube', 'https://youtu.be/a', 'Stream A', 'ready', :v, 30000), "
            "(2, 4, 'vod_url', 'youtube', 'https://youtu.be/b', 'Stream B', 'ready', :v, 30000), "
            "(3, NULL, 'local_file', 'local', NULL, 'File lokal', 'ready', :v, 30000)"),
            {"v": str(GAMING)})
        for cid, sid, status in [(10, 1, "candidate"), (11, 1, "approved"), (12, 1, "rejected"),
                                 (13, 1, "rendered"), (20, 2, "candidate"), (30, 3, "candidate")]:
            conn.execute(text(
                "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, "
                "layout_preset_id, subtitle_style_id, output_video_path) "
                "VALUES (:id, :s, 'auto', :st, 0, 20000, :p, 1, :out)"),
                {"id": cid, "s": sid, "st": status, "p": gaming,
                 "out": "x.mp4" if status == "rendered" else None})
        # override lama di Klip 11 & 12, region deteksi stream A
        for owner, value in (("clip_id", 11), ("clip_id", 12), ("source_stream_id", 1)):
            conn.execute(text(f"INSERT INTO cam_regions ({owner}, role, x, y, w, h) "
                              "VALUES (:v, 'cam', 0.1, 0.1, 0.2, 0.2)"), {"v": value})
    return engine


def test_layout_presets(api, db):
    items = api.get("/api/v1/layout-presets").json()["items"]
    assert [p["code"] for p in items] == ["gaming", "podcast", "irl", "split_two",
                                          "center_crop", "custom"]
    assert items[0]["params"] == {"cam_height_pct": 35} and items[0]["is_builtin"] is True


def test_channels_list_create_and_assign(api, db):
    body = api.get("/api/v1/channels").json()
    assert body["total"] == 1 and body["items"][0]["stream_count"] == 2
    r = api.post("/api/v1/channels", json={"name": "  Rekaman Saya  "})
    assert r.status_code == 201
    created = r.json()
    assert (created["platform"], created["name"], created["external_id"]) == (
        "local", "Rekaman Saya", None)
    dup = api.post("/api/v1/channels", json={"name": "rekaman saya"})
    assert dup.status_code == 409
    assert dup.json()["error"]["fields"] == {"existing_channel_id": str(created["id"])}
    assert api.post("/api/v1/channels", json={"name": "   "}).status_code == 400

    r = api.patch("/api/v1/streams/3/channel", json={"channel_id": created["id"]})
    assert r.status_code == 200
    assert r.json()["stream"]["channel"] == {"id": created["id"], "name": "Rekaman Saya"}
    assert api.patch("/api/v1/streams/3/channel", json={"channel_id": 999}).status_code == 404
    assert api.patch("/api/v1/streams/999/channel", json={"channel_id": 4}).status_code == 404


def test_stream_regions(api, db):
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET suggested_layout_preset_id = :p WHERE id = 1"),
                     {"p": preset_id(db, "gaming")})
        conn.execute(text("INSERT INTO jobs (job_type, source_stream_id, status) "
                          "VALUES ('detect_layout', 1, 'succeeded')"))
    body = api.get("/api/v1/streams/1/regions").json()
    assert body["detected"] is True
    assert body["suggested_layout_preset"]["code"] == "gaming"
    assert body["regions"] == [{"role": "cam", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}]
    assert body["channel"]["name"] == "Kanal Gaming" and body["message"] is None
    assert api.get("/api/v1/streams/99/regions").status_code == 404


def test_stream_regions_no_face_message(api, db):
    with db.begin() as conn:
        conn.execute(text("DELETE FROM cam_regions WHERE source_stream_id = 2"))
        conn.execute(text("UPDATE source_streams SET suggested_layout_preset_id = :p WHERE id = 2"),
                     {"p": preset_id(db, "center_crop")})
        conn.execute(text("INSERT INTO jobs (job_type, source_stream_id, status) "
                          "VALUES ('detect_layout', 2, 'succeeded')"))
    body = api.get("/api/v1/streams/2/regions").json()
    assert body["message"] == "Wajah tidak terdeteksi. Tandai area kamera manual jika ada."


def test_tc017_channel_default_used_by_next_stream(api, db):
    r = api.put("/api/v1/clips/10/regions", json={
        "regions": [CAM, CONTENT], "save_as_channel_default": True, "apply_to_stream_clips": True})
    assert r.status_code == 200
    assert r.json() == {"clip_id": 10, "regions_source": "clip", "affected_clip_ids": [11]}
    # default Kanal terisi
    assert q(db, "SELECT default_layout_preset_id FROM channels WHERE id = 4") == [
        (preset_id(db, "gaming"),)]
    assert {r[0] for r in q(db, "SELECT role FROM cam_regions WHERE channel_id = 4")} == {
        "cam", "content"}
    # Klip 11 (approved) kehilangan override → ikut default; Klip 12 (rejected) tidak tersentuh
    assert q(db, "SELECT count(*) FROM cam_regions WHERE clip_id = 11") == [(0,)]
    assert q(db, "SELECT count(*) FROM cam_regions WHERE clip_id = 12") == [(1,)]
    with db.connect() as conn:
        assert layouts.effective_regions(conn, 11)[0] == "channel"
        assert layouts.effective_regions(conn, 10)[0] == "clip"
        # Stream baru dari Kanal yang sama: Klip memakai region Kanal tanpa koreksi
        source, items = layouts.effective_regions(conn, 20)
    assert source == "channel"
    assert {i["role"]: i["x"] for i in items} == {"cam": 0.65, "content": 0.0}
    channel = api.get("/api/v1/streams/2/regions").json()["channel"]
    assert channel["default_layout_preset"]["code"] == "gaming"
    assert len(channel["default_regions"]) == 2


def test_save_default_without_channel_is_409(api, db):
    r = api.put("/api/v1/clips/30/regions", json={
        "regions": [CAM, CONTENT], "save_as_channel_default": True})
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "INVALID_STATE", "message": "Pilih Kanal dulu."}
    assert q(db, "SELECT count(*) FROM cam_regions WHERE clip_id = 30") == [(0,)]


def test_override_without_default_and_stream_fallback(api, db):
    with db.connect() as conn:
        assert layouts.effective_regions(conn, 10)[0] == "stream"
    r = api.put("/api/v1/clips/10/regions", json={"regions": [CAM, CONTENT]})
    assert r.json()["affected_clip_ids"] == []
    assert q(db, "SELECT count(*) FROM cam_regions WHERE channel_id = 4") == [(0,)]
    # ganti satu role saja: role lain tetap (replace per role)
    api.put("/api/v1/clips/10/regions", json={"regions": [{**CAM, "x": 0.6}]})
    rows = dict(q(db, "SELECT role, x FROM cam_regions WHERE clip_id = 10"))
    assert rows == {"cam": 0.6, "content": 0.0}


@pytest.mark.parametrize(("body", "message"), [
    ({"regions": [CAM]}, "Preset Gaming butuh region cam dan content."),
    ({"regions": [CAM, {**CAM}]}, "Setiap role region hanya boleh sekali."),
    ({"regions": [{**CAM, "x": 0.8}, CONTENT]}, "Region keluar dari frame."),
    ({"regions": [{**CAM, "w": 0.01}, CONTENT]}, None),
    ({"regions": [{**CAM, "role": "mulut"}, CONTENT]}, None),
])
def test_invalid_regions(api, db, body, message):
    r = api.put("/api/v1/clips/10/regions", json=body)
    assert r.status_code == 400
    if message:
        assert r.json()["error"]["message"] == message


def test_preset_without_regions_rejects(api, db):
    with db.begin() as conn:
        conn.execute(text("UPDATE clips SET layout_preset_id = :p WHERE id = 10"),
                     {"p": preset_id(db, "irl")})
    r = api.put("/api/v1/clips/10/regions", json={"regions": [CAM]})
    assert r.json()["error"]["message"] == "Preset ini tidak memakai Region Cam."


def test_rendered_becomes_approved_and_rendering_is_locked(api, db):
    assert api.put("/api/v1/clips/13/regions", json={"regions": [CAM, CONTENT]}).status_code == 200
    assert q(db, "SELECT status FROM clips WHERE id = 13") == [("approved",)]
    with db.begin() as conn:
        conn.execute(text("UPDATE clips SET status = 'rendering' WHERE id = 11"))
    assert api.put("/api/v1/clips/11/regions", json={"regions": [CAM, CONTENT]}).status_code == 409
    assert api.put("/api/v1/clips/999/regions", json={"regions": [CAM, CONTENT]}).status_code == 404


def test_frame_jpeg(api, db):
    r = api.get("/api/v1/media/streams/1/frame", params={"t_ms": 5000, "w": 320})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "max-age=60" in r.headers["cache-control"]
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] == 320 and img.shape[0] == 180
    # token lewat ?t= (untuk <img src>) tanpa header
    r = api.get(f"/api/v1/media/streams/1/frame?t={TOKEN}",
                headers={"X-Klipin-Token": "", "Host": f"127.0.0.1:{PORT}"})
    assert r.status_code == 200


def test_frame_errors(api, db):
    assert api.get("/api/v1/media/streams/1/frame", params={"t_ms": 31_000}).status_code == 400
    assert api.get("/api/v1/media/streams/1/frame", params={"w": 2000}).status_code == 400
    assert api.get("/api/v1/media/streams/99/frame").status_code == 404
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET source_deleted_at = '2026-11-21T00:00:00Z' "
                          "WHERE id = 1"))
    r = api.get("/api/v1/media/streams/1/frame")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SOURCE_DELETED"
