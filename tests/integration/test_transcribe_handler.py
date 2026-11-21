"""T-027: handler Job `transcribe` dengan FFmpeg asli + FakeTranscriber. TC-011–TC-014."""

from pathlib import Path

import pytest
from sqlalchemy import text

from klipin import secrets
from klipin.providers.transcriber import (
    AudioChunk,
    FakeTranscriber,
    TranscriberBadAudioError,
    TranscriberTransientError,
)
from klipin.providers.transcriber.base import MSG_API_KEY, MSG_TRANSIENT
from klipin.worker.handlers import transcribe
from klipin.worker.loop import claim, run_job
from klipin.worker.pipeline import create_job

AUDIO_25MIN = Path(__file__).resolve().parents[1] / "fixtures" / "audio_25min_scream_at_10.flac"
DURATION = 1_500_000


@pytest.fixture
def db(engine, home, memory_keyring, monkeypatch):
    monkeypatch.setattr(transcribe, "BACKOFF_S", (0.0, 0.0, 0.0))
    secrets.set_secret("transcriber_api_key", "kunci-uji")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO source_streams (id, source_type, platform, title, status, video_path, "
            "duration_ms) VALUES (1, 'local_file', 'local', 'Audio 25 menit', 'processing', "
            ":v, :d)"), {"v": str(AUDIO_25MIN), "d": DURATION})
    return engine


@pytest.fixture
def fake(monkeypatch):
    t = FakeTranscriber()
    monkeypatch.setattr(transcribe, "get_transcriber", lambda engine: t)
    return t


def run_transcribe(engine, **cols):
    with engine.begin() as conn:
        job_id = create_job(conn, "transcribe", 1, **cols)
    ctx = claim(engine, heavy=True)
    assert ctx is not None and ctx.id == job_id
    run_job(ctx)
    return job_id


def q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def stored_words(engine):
    return [tuple(r) for r in q(engine, "SELECT start_ms, end_ms, word FROM transcript_words "
                                        "ORDER BY start_ms, id")]


def ideal_words(start_ms=0, end_ms=DURATION, **fake_kwargs):
    """Transkrip satu tarikan tanpa potongan: acuan untuk hasil yang sudah dijahit."""
    r = FakeTranscriber(**fake_kwargs).transcribe(AudioChunk(Path("x"), 0, start_ms, end_ms))
    return [(w.start_ms + start_ms, w.end_ms + start_ms, w.word)
            for u in r.utterances for w in u.words]


def job_row(engine, job_id):
    return q(engine, "SELECT status, error_message FROM jobs WHERE id = :id", id=job_id)[0]


def test_tc011_multi_chunk_stitched(db, fake, home):
    job_id = run_transcribe(db)
    assert job_row(db, job_id) == ("succeeded", None)
    chunks = q(db, "SELECT chunk_index, start_ms, end_ms, status, provider, attempts "
                   "FROM transcription_chunks ORDER BY chunk_index")
    assert chunks == [(0, 0, 602_000, "done", "fake", 1),
                      (1, 600_000, 1_202_000, "done", "fake", 1),
                      (2, 1_200_000, 1_500_000, "done", "fake", 1)]
    for (idx, start, end, *_), call in zip(chunks, fake.calls, strict=True):
        assert (call.index, call.start_ms, call.end_ms) == (idx, start, end)
        assert call.path.is_file() and call.path.suffix == ".flac"  # audio diekstrak FFmpeg
        assert call.path.parent == home / "streams" / "1" / "audio"

    words = stored_words(db)
    starts = [w[0] for w in words]
    assert starts == sorted(starts)
    assert len(set(words)) == len(words)  # tanpa duplikat di zona tumpang tindih
    assert words == ideal_words()  # tanpa kata hilang di sambungan
    assert all(w[0] < w[1] for w in words)
    assert q(db, "SELECT detected_language FROM source_streams") == [("id",)]
    # bahasa dideteksi di potongan pertama, lalu dipakai eksplisit
    assert [c.language for c in fake.calls] == [None, "id", "id"]
    speakers = {s for (s,) in q(db, "SELECT DISTINCT speaker FROM transcript_segments")}
    assert speakers and all(s.startswith("S") for s in speakers)
    # pembicara kalimat yang melintasi sambungan 10:00 tetap satu label
    seg = q(db, "SELECT DISTINCT s.speaker FROM transcript_words w JOIN transcript_segments s "
                "ON s.id = w.segment_id WHERE w.start_ms BETWEEN 600000 AND 604000")
    assert len(seg) == 1
    assert q(db, "SELECT checkpoint FROM jobs WHERE id = :id", id=job_id)[0][0] == (
        '{"chunks_done": 3, "chunks_total": 3}')


def test_tc012_429_retried_only_that_chunk(db, fake):
    fake.failures = {1: [TranscriberTransientError("429 Too Many Requests", 429),
                         TranscriberTransientError("429 Too Many Requests", 429)]}
    job_id = run_transcribe(db)
    assert job_row(db, job_id) == ("succeeded", None)
    assert [c.index for c in fake.calls] == [0, 1, 1, 1, 2]
    assert q(db, "SELECT chunk_index, attempts FROM transcription_chunks ORDER BY chunk_index"
             ) == [(0, 1), (1, 3), (2, 1)]
    log = q(db, "SELECT log_tail FROM jobs WHERE id = :id", id=job_id)[0][0]
    assert "429 Too Many Requests; coba lagi" in log
    assert stored_words(db) == ideal_words()


def test_transient_exhausted_fails_job(db, fake):
    fake.failures = {0: [TranscriberTransientError("503", 503) for _ in range(4)]}
    job_id = run_transcribe(db)
    assert job_row(db, job_id) == ("failed", MSG_TRANSIENT)
    assert q(db, "SELECT status, attempts FROM transcription_chunks WHERE chunk_index = 0"
             ) == [("failed", 4)]
    assert q(db, "SELECT status FROM source_streams") == [("failed",)]


def test_tc013_permanent_failure_then_retry_resumes(db, fake, api):
    fake.failures = {1: [TranscriberBadAudioError("400 corrupt audio")]}
    job_id = run_transcribe(db)
    status, error = job_row(db, job_id)
    assert status == "failed" and "menolak potongan audio" in error
    assert q(db, "SELECT chunk_index, status FROM transcription_chunks ORDER BY chunk_index") == [
        (0, "done"), (1, "failed"), (2, "pending")]

    resp = api.post(f"/api/v1/jobs/{job_id}/retry")
    assert resp.status_code == 202
    fake.calls.clear()
    ctx = claim(db, heavy=True)
    assert ctx.id == resp.json()["job"]["id"]
    run_job(ctx)
    assert job_row(db, ctx.id) == ("succeeded", None)
    assert [c.index for c in fake.calls] == [1, 2]  # potongan 1 (done) tidak dikirim ulang
    assert stored_words(db) == ideal_words()
    assert q(db, "SELECT status FROM source_streams") == [("processing",)]


def test_tc014_missing_api_key_sends_nothing(db, home, memory_keyring, monkeypatch):
    secrets.delete_secret("transcriber_api_key")
    sent = []
    monkeypatch.setattr(FakeTranscriber, "transcribe", lambda self, c, **kw: sent.append(c))
    job_id = run_transcribe(db)
    assert job_row(db, job_id) == ("failed", MSG_API_KEY)
    assert sent == []
    assert q(db, "SELECT count(*) FROM transcription_chunks") == [(0,)]
    assert not (home / "streams" / "1" / "audio").exists()


def test_silent_first_chunk(db, monkeypatch):
    t = FakeTranscriber(silent_ranges=[(0, 602_000)])
    monkeypatch.setattr(transcribe, "get_transcriber", lambda engine: t)
    job_id = run_transcribe(db)
    assert job_row(db, job_id) == ("succeeded", None)
    assert q(db, "SELECT count(*) FROM transcript_segments s JOIN transcription_chunks c "
                 "ON c.id = s.chunk_id WHERE c.chunk_index = 0") == [(0,)]
    assert q(db, "SELECT count(*) FROM transcript_words WHERE word = ''") == [(0,)]
    # potongan hening tidak menetapkan bahasa; potongan berikutnya yang mendeteksi
    assert [c.language for c in t.calls] == [None, None, "id"]
    assert q(db, "SELECT detected_language FROM source_streams") == [("id",)]
    assert stored_words(db) == ideal_words(silent_ranges=[(0, 602_000)])


def test_scope_range_only(db, fake):
    job_id = run_transcribe(db, scope_start_ms=60_000, scope_end_ms=120_000)
    assert job_row(db, job_id) == ("succeeded", None)
    assert q(db, "SELECT start_ms, end_ms FROM transcription_chunks") == [(60_000, 120_000)]
    assert stored_words(db) == ideal_words(60_000, 120_000)
    # Job berrentang tidak mengubah status Stream Sumber / tidak memicu score_highlights
    assert q(db, "SELECT job_type FROM jobs") == [("transcribe",)]


def test_plan_chunks_boundaries():
    plan = transcribe.plan_chunks(0, 1_500_000)
    assert [(p.start_ms, p.end_ms, p.own_start, p.own_end) for p in plan] == [
        (0, 602_000, 0, 601_000),
        (600_000, 1_202_000, 601_000, 1_201_000),
        (1_200_000, 1_500_000, 1_201_000, 1_500_001)]
    assert len(transcribe.plan_chunks(0, 602_000)) == 1
    assert len(transcribe.plan_chunks(0, 602_001)) == 2
    assert transcribe.plan_chunks(5_000, 30_000)[0].own_start == 5_000
