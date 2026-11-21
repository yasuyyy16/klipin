"""T-040: endpoint Klip, transkrip, timeline, waveform, media source (Range). TC-027–TC-032."""

from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import PORT, TOKEN

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VIDEO = FIXTURES / "gaming_facecam_30s.mp4"


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO channels (id, platform, external_id, name) "
                          "VALUES (4, 'youtube', 'UC1', 'NamaStreamer')"))
        conn.execute(text(
            "INSERT INTO source_streams (id, channel_id, source_type, platform, source_url, title, "
            "status, video_path, duration_ms, detected_language) VALUES (1, 4, 'vod_url', "
            "'youtube', 'https://youtu.be/x', 'Stream', 'ready', :v, 600000, 'en')"),
            {"v": str(VIDEO)})
        rows = [(10, "auto", "candidate", 0, 30_000, 87), (11, "auto", "candidate", 60_000, 90_000, 55),
                (12, "live_marker", "candidate", 100_000, 200_000, None),
                (13, "auto", "rejected", 300_000, 330_000, 90),
                (14, "auto", "rendered", 400_000, 430_000, 70)]
        for cid, origin, status, a, b, score in rows:
            conn.execute(text(
                "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, score, "
                "layout_preset_id, subtitle_style_id, output_video_path, rendered_at, title) "
                "VALUES (:id, 1, :o, :st, :a, :b, :sc, 1, 1, :out, :ra, 'Judul')"),
                {"id": cid, "o": origin, "st": status, "a": a, "b": b, "sc": score,
                 "out": "x.mp4" if status == "rendered" else None,
                 "ra": "2026-11-21T00:00:00Z" if status == "rendered" else None})
        conn.execute(text("INSERT INTO transcription_chunks (id, source_stream_id, chunk_index, "
                          "start_ms, end_ms, status) VALUES (1, 1, 0, 0, 600000, 'done')"))
        for sid, a, b, words in [(1, 10_000, 14_000, ["gua", "kaget", "banget"]),
                                 (2, 20_500, 26_000, ["lanjut", "main"])]:
            conn.execute(text("INSERT INTO transcript_segments (id, source_stream_id, chunk_id, "
                              "start_ms, end_ms, speaker, text) VALUES (:i, 1, 1, :a, :b, 'S1', "
                              ":t)"), {"i": sid, "a": a, "b": b, "t": " ".join(words)})
            for k, w in enumerate(words):
                conn.execute(text("INSERT INTO transcript_words (source_stream_id, segment_id, "
                                  "start_ms, end_ms, word, confidence) VALUES (1, :s, :a, :b, :w, "
                                  "0.9)"), {"s": sid, "a": a + k * 1000, "b": a + k * 1000 + 800,
                                            "w": w})
        conn.execute(text("INSERT INTO highlight_windows (source_stream_id, start_ms, end_ms, "
                          "audio_signal, chat_signal, preselected, llm_score, llm_status) VALUES "
                          "(1, 0, 60000, 0.8, 0.5, 1, 70, 'done'), "
                          "(1, 30000, 90000, 0.2, NULL, 0, NULL, 'not_requested')"))
    return engine


def test_list_default_hides_rejected_sorted_by_score(api, db):
    body = api.get("/api/v1/streams/1/clips").json()
    assert body["total"] == 4
    assert [c["id"] for c in body["items"]] == [10, 14, 11, 12]  # skor turun, null terakhir
    first = body["items"][0]
    assert first["duration_ms"] == 30_000 and first["uploads"] == []
    by_start = api.get("/api/v1/streams/1/clips", params={"sort": "start"}).json()["items"]
    assert [c["id"] for c in by_start] == [10, 11, 12, 14]
    rejected = api.get("/api/v1/streams/1/clips", params={"status": "rejected"}).json()
    assert [c["id"] for c in rejected["items"]] == [13]
    assert api.get("/api/v1/streams/1/clips", params={"status": "x"}).status_code == 400
    assert api.get("/api/v1/streams/99/clips").status_code == 404


def test_clip_detail(api, db):
    d = api.get("/api/v1/clips/10").json()
    assert d["layout_preset"]["code"] == "gaming"
    assert d["regions"] == {"source": None, "items": []}
    assert d["available_languages"] == ["source", "id"] and d["detected_language"] == "en"
    assert d["output"] is None and d["needs_rerender"] is False
    assert d["score_breakdown"] == {"audio": None, "chat": None, "llm": None, "partial": False}
    rendered = api.get("/api/v1/clips/14").json()
    assert rendered["output"]["video_url"] == "/api/v1/media/clips/14/video"
    assert api.get("/api/v1/clips/999").status_code == 404


def test_tc027_approve_reject_restore(api, db):
    assert api.post("/api/v1/clips/10/approve").json() == {"id": 10, "status": "approved"}
    assert api.post("/api/v1/clips/10/approve").json()["status"] == "approved"  # idempoten
    assert api.post("/api/v1/clips/10/reject").json()["status"] == "rejected"
    assert api.post("/api/v1/clips/10/restore").json()["status"] == "candidate"
    api.post("/api/v1/clips/10/approve")
    assert api.post("/api/v1/clips/10/unapprove").json()["status"] == "candidate"
    r = api.post("/api/v1/clips/13/approve")  # rejected → approve tidak sah
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"


def test_tc028_approve_100_seconds_rejected_and_db_check(api, db):
    r = api.post("/api/v1/clips/12/approve")
    assert r.status_code == 400
    assert r.json()["error"]["fields"] == {"duration_ms": "Durasi klip harus 15–90 detik."}
    with pytest.raises(Exception, match="CHECK"), db.begin() as conn:
        conn.execute(text("UPDATE clips SET status = 'approved' WHERE id = 12"))


def test_tc029_manual_clip_with_existing_words(api, db):
    r = api.post("/api/v1/streams/1/clips", json={"start_ms": 5_000, "end_ms": 45_000})
    assert r.status_code == 201
    clip = r.json()
    assert (clip["origin"], clip["status"], clip["duration_ms"]) == ("manual", "candidate", 40_000)
    assert clip["title"] == "NamaStreamer - 00:05"
    words = api.get("/api/v1/streams/1/transcript",
                    params={"from_ms": clip["start_ms"], "to_ms": clip["end_ms"]}).json()
    assert [w["word"] for s in words["segments"] for w in s["words"]] == [
        "gua", "kaget", "banget", "lanjut", "main"]
    bad = api.post("/api/v1/streams/1/clips", json={"start_ms": 50_000, "end_ms": 40_000})
    assert bad.status_code == 400
    assert api.post("/api/v1/streams/1/clips",
                    json={"start_ms": 590_000, "end_ms": 700_000}).status_code == 400


def test_tc030_snap_to_sentence_boundary(api, db):
    r = api.post("/api/v1/clips/10/snap", json={"edge": "end", "position_ms": 15_200})
    assert r.json() == {"snapped_ms": 14_000, "segment_id": 1}
    r = api.post("/api/v1/clips/10/snap", json={"edge": "start", "position_ms": 19_000})
    assert r.json() == {"snapped_ms": 20_500, "segment_id": 2}
    far = api.post("/api/v1/clips/10/snap", json={"edge": "end", "position_ms": 40_000})
    assert far.json() == {"snapped_ms": 40_000, "segment_id": None}


def test_tc031_subtitle_override_keeps_transcript_word(api, db):
    word_id = q(db, "SELECT id FROM transcript_words WHERE word = 'gua'")[0][0]
    r = api.patch("/api/v1/clips/10", json={
        "subtitle_overrides": {"words": {str(word_id): "gue"}, "line_breaks_after_word_ids": []}})
    assert r.status_code == 200
    assert r.json()["subtitle_overrides"]["words"] == {str(word_id): "gue"}
    assert q(db, "SELECT word FROM transcript_words WHERE id = :i", i=word_id) == [("gua",)]
    bad = api.patch("/api/v1/clips/10", json={"subtitle_overrides": {"words": {"abc": "x"}}})
    assert bad.status_code == 400


def test_tc032_edit_rendered_becomes_approved(api, db):
    r = api.patch("/api/v1/clips/14", json={"title": "Judul baru"})
    body = r.json()
    assert (body["status"], body["needs_rerender"], body["title"]) == ("approved", True, "Judul baru")


def test_patch_rules(api, db):
    api.post("/api/v1/clips/10/approve")
    r = api.patch("/api/v1/clips/10", json={"end_ms": 120_000})  # approved jadi 120 dtk
    assert r.status_code == 400 and "15–90" in r.json()["error"]["message"]
    assert api.patch("/api/v1/clips/11", json={"end_ms": 200_000}).status_code == 200  # candidate
    assert api.patch("/api/v1/clips/11", json={"start_ms": None}).status_code == 400
    with db.begin() as conn:
        conn.execute(text("UPDATE clips SET status = 'rendering' WHERE id = 14"))
    assert api.patch("/api/v1/clips/14", json={"title": "x"}).status_code == 409
    assert api.patch("/api/v1/clips/10", json={"layout_preset_id": 999}).status_code == 400
    # BR-008: gaya per kata + Bahasa Tampil id → peringatan mode kalimat
    word_style = q(db, "SELECT id FROM subtitle_styles WHERE mode = 'word_highlight' LIMIT 1")[0][0]
    r = api.patch("/api/v1/clips/10", json={"subtitle_language": "id",
                                            "subtitle_style_id": word_style})
    assert r.json()["warnings"] == ["Terjemahan memakai mode kalimat"]


def test_tc035_translation_rejected_for_indonesian_stream(api, db):
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET detected_language = 'id'"))
    r = api.patch("/api/v1/clips/10", json={"subtitle_language": "id"})
    assert r.status_code == 400
    assert api.get("/api/v1/clips/10").json()["available_languages"] == ["source"]


def test_transcript_range_limit(api, db):
    r = api.get("/api/v1/streams/1/transcript", params={"from_ms": 0, "to_ms": 31 * 60_000})
    assert r.status_code == 400


def test_timeline(api, db):
    body = api.get("/api/v1/streams/1/timeline").json()
    assert len(body["buckets"]) == 20  # 600 dtk / 30 dtk
    assert body["buckets"][0] == {"start_ms": 0, "audio": 0.8, "chat": 0.5, "llm": 0.7}
    assert body["buckets"][2] == {"start_ms": 60_000, "audio": 0.2, "chat": None, "llm": None}
    assert body["buckets"][5]["audio"] == 0.0
    assert [c["id"] for c in body["clips"]] == [10, 11, 12, 13, 14]


def test_waveform(api, db, home):
    r = api.get("/api/v1/streams/1/waveform", params={"from_ms": 0, "to_ms": 10_000, "points": 100})
    body = r.json()
    assert len(body["peaks"]) == 100 and 0 < max(body["peaks"]) <= 1
    assert (home / "streams" / "1" / "cache" / "waveform_0_10000_100.json").is_file()
    assert api.get("/api/v1/streams/1/waveform",
                   params={"from_ms": 0, "to_ms": 700_000}).status_code == 400
    assert api.get("/api/v1/streams/1/waveform",
                   params={"from_ms": 0, "to_ms": 1000, "points": 5000}).status_code == 400


def test_source_video_with_range(api, db):
    size = VIDEO.stat().st_size
    full = api.get(f"/api/v1/media/streams/1/source?t={TOKEN}",
                   headers={"X-Klipin-Token": "", "Host": f"127.0.0.1:{PORT}"})
    assert full.status_code == 200 and len(full.content) == size
    assert full.headers["content-type"] == "video/mp4"
    part = api.get("/api/v1/media/streams/1/source", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == f"bytes 100-199/{size}"
    assert part.content == VIDEO.read_bytes()[100:200]


def test_source_deleted(api, db):
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET source_deleted_at = '2026-11-21T00:00:00Z'"))
    for url in ("/api/v1/media/streams/1/source",
                "/api/v1/streams/1/waveform?from_ms=0&to_ms=1000"):
        r = api.get(url)
        assert r.status_code == 409 and r.json()["error"]["code"] == "SOURCE_DELETED"
    r = api.patch("/api/v1/clips/10", json={"end_ms": 20_000})
    assert r.status_code == 409
    assert api.post("/api/v1/streams/1/clips",
                    json={"start_ms": 0, "end_ms": 20_000}).status_code == 409
