"""T-039: handler `score_highlights` (audio & chat fixture asli + FakeJudge) dan rescore. TC-026."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from klipin import secrets
from klipin.providers.llm import FakeJudge, JudgeUnavailable
from klipin.worker.handlers import score_highlights as sh
from klipin.worker.handlers.download import import_chat
from klipin.worker.loop import claim, run_job
from klipin.worker.pipeline import create_job

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AUDIO = FIXTURES / "audio_25min_scream_at_10.flac"
DURATION = 1_500_000


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


@pytest.fixture
def db(engine, home, memory_keyring):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO channels (id, platform, external_id, name) "
                          "VALUES (4, 'youtube', 'UC1', 'NamaStreamer')"))
        conn.execute(text(
            "INSERT INTO source_streams (id, channel_id, source_type, platform, source_url, "
            "title, status, video_path, duration_ms, detected_language, has_chat) VALUES "
            "(1, 4, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream', 'processing', :v, :d, "
            "'id', 1)"), {"v": str(AUDIO), "d": DURATION})
        conn.execute(text(  # satu segmen transkrip di sekitar teriakan untuk prompt LLM
            "INSERT INTO transcription_chunks (id, source_stream_id, chunk_index, start_ms, "
            "end_ms, status) VALUES (1, 1, 0, 0, 1500000, 'done')"))
        conn.execute(text(
            "INSERT INTO transcript_segments (source_stream_id, chunk_id, start_ms, end_ms, "
            "speaker, text) VALUES (1, 1, 599000, 603000, 'S1', 'aaa kaget wkwk')"))
    import_chat(engine, 1, FIXTURES / "live_chat_spike.jsonl")
    return engine


@pytest.fixture
def fake(monkeypatch):
    judge = FakeJudge()
    monkeypatch.setattr(sh, "get_judge", lambda engine: judge)
    return judge


def run_score(engine):
    with engine.begin() as conn:
        create_job(conn, "score_highlights", 1)
    ctx = claim(engine, heavy=True)
    run_job(ctx)
    return q(engine, "SELECT status, error_message, log_tail FROM jobs WHERE id = :i", i=ctx.id)[0]


def clips(engine):
    return q(engine, "SELECT id, origin, status, start_ms, end_ms, score, score_audio, score_chat, "
                     "score_llm, score_partial, category, title, layout_preset_id "
                     "FROM clips ORDER BY score DESC, start_ms")


def test_scores_scream_and_chat_spike_into_top_candidate(db, fake):
    status, error, log = run_score(db)
    assert (status, error) == ("succeeded", None)
    result = clips(db)
    assert 1 <= len(result) <= 3  # 25 menit → BR-006 maks. 3
    top = result[0]
    assert top.origin == "auto" and top.status == "candidate"
    assert abs(top.start_ms - 570_000) <= 30_000  # jendela di sekitar teriakan + lonjakan chat
    # teriakan 10:00–10:03 tercakup salah satu kandidat
    assert any(c.start_ms <= 600_000 and c.end_ms >= 603_000 for c in result)
    assert 15_000 <= top.end_ms - top.start_ms <= 90_000
    assert top.score >= 80 and top.score_audio == 1.0 and top.score_partial == 0
    assert top.score_llm is not None and top.category == "hype"
    assert top.title.startswith("Momen detik")
    # preset: tanpa default Kanal & saran → center_crop
    assert top.layout_preset_id == q(db, "SELECT id FROM layout_presets "
                                         "WHERE code = 'center_crop'")[0][0]
    assert all(c.score >= 40 for c in result)
    windows = q(db, "SELECT count(*), sum(preselected), sum(llm_status = 'done') "
                    "FROM highlight_windows")[0]
    assert windows[0] == 49 and windows[1] == windows[2] == len(set(fake.calls))
    assert "lolos pra-seleksi" in log


def test_prompt_contains_transcript_near_window(db, monkeypatch):
    seen = []

    class Spy(FakeJudge):
        def judge(self, window, *, should_cancel=None):
            seen.append(window)
            return super().judge(window)

    monkeypatch.setattr(sh, "get_judge", lambda engine: Spy())
    run_score(db)
    near = [w for w in seen if w.start_ms == 570_000]
    assert near and near[0].transcript == ["[29.0] S1: aaa kaget wkwk"]
    assert near[0].language == "id"


def test_without_llm_scores_are_partial_with_default_title(db, monkeypatch):
    def unavailable(engine):
        raise JudgeUnavailable("API key LLM belum diisi. Skor memakai Sinyal Audio dan Chat saja.")

    monkeypatch.setattr(sh, "get_judge", unavailable)
    status, _, log = run_score(db)
    assert status == "succeeded"
    assert "API key LLM belum diisi" in log
    top = clips(db)[0]
    assert top.score_partial == 1 and top.score_llm is None and top.category is None
    assert top.title == f"NamaStreamer - {top.start_ms // 60000:02d}:{top.start_ms // 1000 % 60:02d}"


def test_channel_default_preset_used(db, fake):
    with db.begin() as conn:
        conn.execute(text("UPDATE channels SET default_layout_preset_id = "
                          "(SELECT id FROM layout_presets WHERE code = 'gaming')"))
    run_score(db)
    gaming = q(db, "SELECT id FROM layout_presets WHERE code = 'gaming'")[0][0]
    assert {c.layout_preset_id for c in clips(db)} == {gaming}


def test_transcribed_range_limits_windows(db, fake):
    with db.begin() as conn:
        conn.execute(text("INSERT INTO jobs (job_type, source_stream_id, status, checkpoint) "
                          "VALUES ('transcribe', 1, 'succeeded', :c)"),
                     {"c": json.dumps({"range": {"start_ms": 0, "end_ms": 300_000}})})
    run_score(db)
    assert q(db, "SELECT max(end_ms) FROM highlight_windows")[0][0] <= 300_000
    assert all(c.end_ms <= 300_000 for c in clips(db))


def test_missing_video_fails_first_run(db, fake):
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET video_path = NULL"))
    status, error, _ = run_score(db)
    assert (status, error) == ("failed", sh.MSG_NO_SOURCE)


def test_tc026_rescore_replaces_candidates_only(api, db, monkeypatch):
    first = FakeJudge()
    monkeypatch.setattr(sh, "get_judge", lambda engine: first)
    run_score(db)
    original = clips(db)
    assert original
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET status = 'ready'"))
        conn.execute(text("UPDATE clips SET status = 'approved' WHERE id = :i"),
                     {"i": original[0].id})
        conn.execute(text(
            "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, "
            "layout_preset_id, subtitle_style_id, output_video_path) VALUES "
            "(900, 1, 'live_marker', 'candidate', 100000, 130000, 1, 1, NULL), "
            "(901, 1, 'auto', 'rendered', 1200000, 1230000, 1, 1, 'x.mp4')"))
        conn.execute(text("UPDATE settings SET value = '{\"audio\": 0.6, \"chat\": 0.2, "
                          "\"llm\": 0.2}' WHERE key = 'score_weights'"))
    kept_before = q(db, "SELECT id, status, start_ms, end_ms FROM clips WHERE id IN (:a, 900, 901)",
                    a=original[0].id)

    second = FakeJudge()
    monkeypatch.setattr(sh, "get_judge", lambda engine: second)
    r = api.post("/api/v1/streams/1/rescore")
    assert r.status_code == 202 and r.json()["job"]["job_type"] == "score_highlights"
    assert q(db, "SELECT status FROM source_streams") == [("processing",)]
    run_job(claim(db, heavy=True))

    assert second.calls == []  # jendela `done` tidak dinilai ulang
    assert q(db, "SELECT id, status, start_ms, end_ms FROM clips WHERE id IN (:a, 900, 901)",
             a=original[0].id) == kept_before
    new = [c for c in clips(db) if c.origin == "auto" and c.status == "candidate"]
    assert {c.id for c in new}.isdisjoint({c.id for c in original})
    for c in new:  # tidak menimpa rentang Klip yang dipertahankan (BR-005)
        assert c.start_ms >= original[0].end_ms - 5000 or c.end_ms <= original[0].start_ms + 5000
    # bobot baru dipakai: audio 0,6 → skor teratas naik
    assert new[0].score == round(100 * (0.6 * new[0].score_audio + 0.2 * new[0].score_chat
                                        + 0.2 * new[0].score_llm / 100))


def test_rescore_requires_ready(api, db):
    r = api.post("/api/v1/streams/1/rescore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    assert api.post("/api/v1/streams/99/rescore").status_code == 404


def test_pipeline_ready_after_scoring(db, fake):
    with db.begin() as conn:
        conn.execute(text("INSERT INTO jobs (job_type, source_stream_id, status) "
                          "VALUES ('detect_layout', 1, 'succeeded')"))
    secrets.set_secret("llm_api_key", "x")
    run_score(db)
    assert q(db, "SELECT status FROM source_streams") == [("ready",)]
