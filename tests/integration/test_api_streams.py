"""T-022: POST /streams/inspect, POST /streams (vod), GET /streams, GET /streams/{id}.

TC-001–TC-004. yt-dlp diarahkan ke respons tersimpan `tests/fixtures/ytdlp/` (tanpa jaringan).
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from yt_dlp.utils import DownloadError

from klipin import streams
from klipin.media import ytdlp
from klipin.worker.handlers import fake
from tests.integration.test_pipeline import run_until_idle

SAVED = Path(__file__).resolve().parents[1] / "fixtures" / "ytdlp"
VOD_URL = "https://www.youtube.com/watch?v=abc123XYZ00"
GB = 10**9


def saved(name: str) -> dict:
    return json.loads((SAVED / name).read_text(encoding="utf-8"))


class FakeYDL:
    """YoutubeDL palsu: `info` atau `error` diatur per tes."""

    info: dict | None = None
    error: str | None = None
    calls = 0

    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        FakeYDL.calls += 1
        if FakeYDL.error:
            raise DownloadError(FakeYDL.error)
        return FakeYDL.info


@pytest.fixture
def ydl(monkeypatch):
    real = ytdlp.inspect
    monkeypatch.setattr(ytdlp, "inspect", lambda url: real(url, ydl_cls=FakeYDL))
    monkeypatch.setattr(streams, "disk_free_bytes", lambda path: 500 * GB)
    FakeYDL.info, FakeYDL.error, FakeYDL.calls = saved("youtube_vod_chat.json"), None, 0
    return FakeYDL


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


# --- inspect ------------------------------------------------------------------------------

def test_inspect_returns_metadata_without_creating_rows(api, engine, ydl):
    r = api.post("/api/v1/streams/inspect", json={"url": VOD_URL})
    assert r.status_code == 200
    assert r.json() == {
        "platform": "youtube", "external_video_id": "abc123XYZ00",
        "title": "Main horor sampai pagi",
        "channel": {"external_id": "UCabcdefghijklmnopqrstuv", "name": "NamaStreamer",
                    "known_channel_id": None},
        "duration_ms": 10_845_000, "is_live": False, "has_chat_replay": True,
        "estimated_size_bytes": 6_138_062_134, "disk_free_bytes": 500 * GB,
    }
    assert count(engine, "source_streams") == count(engine, "channels") == 0


def test_tc002_url_not_supported(api, engine, ydl):
    for path in ("/api/v1/streams/inspect", "/api/v1/streams"):
        r = api.post(path, json={"url": "https://vimeo.com/123", "mode": "vod"})
        assert r.status_code == 400
        assert r.json()["error"] == {
            "code": "URL_NOT_SUPPORTED",
            "message": "URL tidak dikenali. Gunakan link VOD YouTube atau Kick."}
    assert ydl.calls == 0  # ditolak sebelum yt-dlp dipanggil
    assert count(engine, "source_streams") == 0


def test_inspect_upstream_error_is_502(api, ydl):
    ydl.error = "ERROR: [youtube] abc123XYZ00: Video unavailable"
    r = api.post("/api/v1/streams/inspect", json={"url": VOD_URL})
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "UPSTREAM_ERROR"
    assert "Perbarui yt-dlp" in err["message"]
    assert "unavailable" not in err["message"]  # detail teknis hanya di log


def test_inspect_timeout_is_502(api, ydl, monkeypatch):
    import threading
    release = threading.Event()
    monkeypatch.setattr(streams, "INSPECT_TIMEOUT_S", 0.2)
    monkeypatch.setattr(ytdlp, "inspect", lambda url: release.wait(5))
    try:
        r = api.post("/api/v1/streams/inspect", json={"url": VOD_URL})
    finally:
        release.set()
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_inspect_knows_existing_channel(api, engine, ydl):
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO channels (id, platform, external_id, name) "
                             "VALUES (4, 'youtube', 'UCabcdefghijklmnopqrstuv', 'Lama')")
    body = api.post("/api/v1/streams/inspect", json={"url": VOD_URL}).json()
    assert body["channel"]["known_channel_id"] == 4


# --- buat Stream Sumber -------------------------------------------------------------------

def test_tc001_import_vod_creates_stream_and_download_job(api, engine, ydl, monkeypatch):
    r = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"})
    assert r.status_code == 201
    body = r.json()
    stream, job = body["stream"], body["job"]
    assert stream["status"] == "queued"
    assert (stream["source_type"], stream["platform"]) == ("vod_url", "youtube")
    assert stream["title"] == "Main horor sampai pagi"
    assert stream["channel"]["name"] == "NamaStreamer"
    assert (job["job_type"], job["status"], job["source_stream_id"]) == (
        "download", "queued", stream["id"])
    assert rows(engine, "SELECT external_video_id, source_url, duration_ms FROM source_streams"
                ) == [("abc123XYZ00", VOD_URL, 10_845_000)]
    assert rows(engine, "SELECT platform, external_id, name FROM channels") == [
        ("youtube", "UCabcdefghijklmnopqrstuv", "NamaStreamer")]

    # Setelah download selesai (handler palsu): processing → detect_layout + transcribe dibuat.
    monkeypatch.setattr(fake, "STEP_S", 0.0)
    run_until_idle(engine)
    job_types = {t for (t,) in rows(engine, "SELECT job_type FROM jobs")}
    assert {"download", "detect_layout", "transcribe"} <= job_types
    detail = api.get(f"/api/v1/streams/{stream['id']}").json()
    assert detail["status"] == "ready"  # pipeline palsu berjalan sampai akhir
    assert detail["active_jobs"] == []


def test_import_reuses_channel_and_updates_name(api, engine, ydl):
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO channels (id, platform, external_id, name) "
                             "VALUES (4, 'youtube', 'UCabcdefghijklmnopqrstuv', 'Nama lama')")
    stream = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"}).json()["stream"]
    assert stream["channel"] == {"id": 4, "name": "NamaStreamer"}
    assert stream["channel_id"] == 4
    assert count(engine, "channels") == 1


def test_tc003_insufficient_disk(api, engine, ydl, monkeypatch):
    monkeypatch.setattr(streams, "disk_free_bytes", lambda path: 4_100_000_000)
    r = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "INSUFFICIENT_DISK"
    required = int(6_138_062_134 * 1.5)
    assert err["fields"] == {"required_bytes": str(required), "free_bytes": "4100000000"}
    assert err["message"] == ("Butuh ±9,2 GB, tersedia 4,1 GB. "
                              "Kosongkan ruang atau hapus video sumber lama.")
    assert count(engine, "source_streams") == count(engine, "jobs") == 0


def test_disk_check_skipped_when_size_unknown(api, ydl, monkeypatch):
    ydl.info = saved("youtube_vod_chat.json")
    for f in ydl.info["requested_formats"]:
        f.pop("filesize", None), f.pop("filesize_approx", None), f.pop("tbr", None)
    monkeypatch.setattr(streams, "disk_free_bytes", lambda path: 1)
    assert api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"}).status_code == 201


def test_tc004_duplicate_import(api, engine, ydl):
    first = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"})
    assert first.status_code == 201
    again = api.post("/api/v1/streams", json={"url": "https://youtu.be/abc123XYZ00",
                                              "mode": "vod"})
    assert again.status_code == 409
    err = again.json()["error"]
    assert err["code"] == "INVALID_STATE"
    assert err["fields"] == {"existing_stream_id": str(first.json()["stream"]["id"])}
    assert count(engine, "source_streams") == 1


def test_duplicate_allowed_after_failed(api, engine, ydl):
    first = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"}).json()
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE source_streams SET status = 'failed'")
        conn.exec_driver_sql("UPDATE jobs SET status = 'failed'")
    second = api.post("/api/v1/streams", json={"url": VOD_URL, "mode": "vod"})
    assert second.status_code == 201
    assert second.json()["stream"]["id"] != first["stream"]["id"]


def test_vod_mode_on_live_url_suggests_record_live(api, engine, ydl):
    ydl.info = saved("youtube_live.json")
    r = api.post("/api/v1/streams", json={"url": "https://www.youtube.com/watch?v=liveNOW1234",
                                          "mode": "vod"})
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "INVALID_STATE",
                                 "message": "Stream ini masih live. Gunakan Rekam Live?"}
    assert count(engine, "source_streams") == 0


@pytest.mark.parametrize("body", [{"url": VOD_URL}, {"url": VOD_URL, "mode": "x"},
                                  {"url": "", "mode": "vod"},
                                  {"url": VOD_URL, "mode": "live"}])
def test_create_validation(api, engine, ydl, body):
    r = api.post("/api/v1/streams", json=body)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert count(engine, "source_streams") == 0


# --- daftar & detail ----------------------------------------------------------------------

@pytest.fixture
def seeded(engine, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"x" * 1234)
    out = tmp_path / "klip.mp4"
    out.write_bytes(b"y" * 100)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO channels (id, platform, external_id, name) "
                             "VALUES (4, 'youtube', 'UC1', 'Kanal A')")
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, channel_id, source_type, platform, source_url, title, "
            "status, video_path, suggested_layout_preset_id, has_chat, created_at) VALUES "
            f"(1, 4, 'vod_url', 'youtube', 'https://youtu.be/a', 'Lama', 'ready', '{video}', 1, 1, "
            "'2026-11-01T00:00:00Z'), "
            "(2, NULL, 'vod_url', 'kick', 'https://kick.com/b', 'Baru', 'downloading', NULL, "
            "NULL, 0, '2026-11-02T00:00:00Z')")
        conn.exec_driver_sql(
            "INSERT INTO clips (source_stream_id, origin, status, start_ms, end_ms, "
            "layout_preset_id, subtitle_style_id, output_video_path) VALUES "
            "(1, 'auto', 'candidate', 0, 30000, 1, 1, NULL), "
            "(1, 'auto', 'candidate', 40000, 70000, 1, 1, NULL), "
            f"(1, 'auto', 'rendered', 80000, 110000, 1, 1, '{out}')")
        conn.exec_driver_sql("INSERT INTO jobs (job_type, source_stream_id, status, progress_pct)"
                             " VALUES ('download', 2, 'running', 40)")
    return engine


def test_list_streams_newest_first_with_counts_and_sizes(api, seeded):
    body = api.get("/api/v1/streams").json()
    assert body["total"] == 2
    assert [s["id"] for s in body["items"]] == [2, 1]
    old = body["items"][1]
    assert old["channel"] == {"id": 4, "name": "Kanal A"}
    assert old["clip_counts"]["candidate"] == 2
    assert old["clip_counts"]["rendered"] == 1
    assert old["storage"] == {"source_bytes": 1234, "rendered_bytes": 100,
                              "source_deleted": False}
    assert body["items"][0]["channel"] is None


def test_list_streams_filter_and_paging(api, seeded):
    body = api.get("/api/v1/streams", params={"status": "ready,failed"}).json()
    assert [s["id"] for s in body["items"]] == [1]
    page = api.get("/api/v1/streams", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and [s["id"] for s in page["items"]] == [1]


@pytest.mark.parametrize("params", [{"status": "paused"}, {"limit": 0}, {"offset": -1}])
def test_list_streams_rejects_bad_params(api, seeded, params):
    assert api.get("/api/v1/streams", params=params).status_code == 400


def test_stream_detail(api, seeded):
    d = api.get("/api/v1/streams/1").json()
    assert d["has_chat"] is True
    assert d["suggested_layout_preset"]["id"] == 1
    assert d["active_jobs"] == []
    d2 = api.get("/api/v1/streams/2").json()
    assert d2["active_jobs"][0] == {"id": d2["active_jobs"][0]["id"], "job_type": "download",
                                    "status": "running", "progress_pct": 40, "stage": None,
                                    "awaiting_confirmation": False}
    r = api.get("/api/v1/streams/99")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
