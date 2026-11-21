"""T-023: handler Job `download` + impor chat replay (INT-02) ke `chat_messages`.

Video diunduh dengan yt-dlp sungguhan dari server HTTP lokal (fixture), chat dari
`tests/fixtures/live_chat_spike.jsonl`. Tanpa jaringan.
"""

import functools
import shutil

import pytest
from sqlalchemy import text

from klipin.config import get_config
from klipin.media import chat_replay, ytdlp
from klipin.worker.handlers import HANDLERS, download, get_handler
from klipin.worker.loop import claim, run_job
from klipin.worker.pipeline import create_job
from tests.unit.test_media_ytdlp import FIXTURES, _RangeServer, local_info

CHAT = FIXTURES / "live_chat_spike.jsonl"


@pytest.fixture
def server():
    with _RangeServer((FIXTURES / "no_audio_10s.mp4").read_bytes()) as s:
        yield s


@pytest.fixture
def db(engine, home):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO source_streams (id, source_type, platform, source_url, title, "
            "external_video_id) VALUES (1, 'vod_url', 'youtube', "
            "'https://www.youtube.com/watch?v=fixture01', 'Stream uji', 'fixture01')")
        create_job(conn, "download", 1)
    return engine


def ctx_for(engine):
    ctx = claim(engine, heavy=True)
    assert ctx is not None and ctx.job_type == "download"
    return ctx


def copy_chat(url, dest, should_cancel):
    dest.mkdir(parents=True, exist_ok=True)
    return shutil.copyfile(CHAT, dest / "chat.json")


def fixture_download(server):
    return functools.partial(ytdlp.download_vod, info=local_info(server.url))


def one(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).one()


def all_rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


def test_download_video_and_import_chat(db, home, server):
    ctx = ctx_for(db)
    download.run(ctx, download=fixture_download(server), fetch_chat=copy_chat)

    video = home / "streams" / "1" / "source.mp4"
    assert video.read_bytes() == server.payload
    assert (home / "streams" / "1" / "chat.json").is_file()
    assert one(db, "SELECT video_path, video_width, video_height, video_fps, has_chat "
               "FROM source_streams") == (str(video), 960, 540, 30.0, 1)
    assert one(db, "SELECT progress_pct, stage FROM jobs") == (100, "Selesai")
    assert ctx.checkpoint == {"video_done": True, "video_path": str(video)}

    assert one(db, "SELECT count(*) FROM chat_messages")[0] == 250
    # offset_ms = videoOffsetTimeMsec
    assert all_rows(db, "SELECT offset_ms, message FROM chat_messages ORDER BY offset_ms LIMIT 2"
                    )[0] == (0, "halo bang")
    spike = all_rows(db, "SELECT offset_ms, is_reaction FROM chat_messages "
                     "WHERE offset_ms >= 600000 AND offset_ms < 610000 ORDER BY offset_ms")
    assert [o for o, _ in spike] == list(range(600_000, 610_000, 1000))
    assert all(r == 1 for _, r in spike)
    assert one(db, "SELECT max(is_reaction) FROM chat_messages WHERE message = 'halo bang'"
               )[0] == 0
    assert one(db, "SELECT min(is_reaction) FROM chat_messages WHERE message = 'gg'")[0] == 1
    assert one(db, "SELECT offset_ms, author, message FROM chat_messages WHERE kind = 'donation'"
               ) == (305_000, "donatur1", "semangat bang")
    assert one(db, "SELECT offset_ms, message FROM chat_messages WHERE kind = 'membership'"
               ) == (905_000, "Welcome to the channel!")


def test_chat_failure_does_not_fail_job(db, server):
    with db.begin() as conn:  # sisa impor lama harus ikut dibersihkan
        conn.exec_driver_sql("INSERT INTO chat_messages (source_stream_id, offset_ms, message) "
                             "VALUES (1, 0, 'lama')")
        conn.exec_driver_sql("UPDATE source_streams SET has_chat = 1")

    def broken(url, dest, should_cancel):
        raise ytdlp.YtdlpError("HTTP Error 403: Forbidden")

    ctx = ctx_for(db)
    run_job_with(ctx, fixture_download(server), broken)
    assert one(db, "SELECT status FROM jobs WHERE id = 1")[0] == "succeeded"
    assert one(db, "SELECT has_chat, status FROM source_streams") == (0, "processing")
    assert one(db, "SELECT count(*) FROM chat_messages")[0] == 0
    assert download.MSG_CHAT_FAILED in one(db, "SELECT log_tail FROM jobs WHERE id = 1")[0]


def test_no_chat_replay(db, server):
    download.run(ctx_for(db), download=fixture_download(server),
                 fetch_chat=lambda url, dest, should_cancel: None)
    assert one(db, "SELECT has_chat FROM source_streams")[0] == 0


def test_kick_skips_chat(db, server):
    with db.begin() as conn:
        conn.exec_driver_sql("UPDATE source_streams SET platform = 'kick'")

    def never(*a, **k):
        raise AssertionError("chat Kick tidak boleh diambil")

    download.run(ctx_for(db), download=fixture_download(server), fetch_chat=never)
    assert one(db, "SELECT has_chat FROM source_streams")[0] == 0


def test_retry_skips_finished_video(db, home, server):
    video = home / "streams" / "1" / "source.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"sudah")
    ctx = ctx_for(db)
    ctx.checkpoint = {"video_done": True, "video_path": str(video)}

    def never(*a, **k):
        raise AssertionError("video tidak boleh diunduh ulang")

    download.run(ctx, download=never, fetch_chat=copy_chat)
    assert server.ranges == []
    assert one(db, "SELECT has_chat FROM source_streams")[0] == 1


def test_partial_video_is_resumed(db, home, server):
    dest = home / "streams" / "1"
    dest.mkdir(parents=True)
    half = len(server.payload) // 2
    (dest / "source.mp4.part").write_bytes(server.payload[:half])
    download.run(ctx_for(db), download=fixture_download(server), fetch_chat=copy_chat)
    assert server.ranges == [f"bytes={half}-"]
    assert (dest / "source.mp4").read_bytes() == server.payload


def run_job_with(ctx, dl, chat):
    """run_job asli (status akhir + pipeline) dengan handler yang memakai unduhan uji."""
    original = HANDLERS["download"]
    HANDLERS["download"] = lambda c: download.run(c, download=dl, fetch_chat=chat)
    try:
        run_job(ctx)
    finally:
        HANDLERS["download"] = original


def test_video_failure_fails_job_and_stream(db, server):
    ctx = ctx_for(db)
    run_job_with(ctx, functools.partial(ytdlp.download_vod,
                                        info=local_info(server.url, "/hilang.mp4")), copy_chat)
    status, error = one(db, "SELECT status, error_message FROM jobs WHERE id = 1")
    assert status == "failed"
    assert error == ytdlp.MSG_YTDLP_FAILED
    assert one(db, "SELECT status, error_message FROM source_streams") == (
        "failed", ytdlp.MSG_YTDLP_FAILED)
    assert "404" in one(db, "SELECT log_tail FROM jobs WHERE id = 1")[0]


def test_disk_full_message(db):
    def full(url, dest, **kw):
        raise ytdlp.YtdlpError("ERROR: unable to write data: [Errno 28] No space left on device")

    run_job_with(ctx_for(db), full, copy_chat)
    assert one(db, "SELECT error_message FROM jobs WHERE id = 1")[0] == download.MSG_DISK_FULL


def test_real_handler_registered_and_used_outside_fake_mode(db, home, server, monkeypatch):
    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    monkeypatch.setattr(ytdlp, "download_vod", fixture_download(server))
    monkeypatch.setattr(ytdlp, "download_live_chat", copy_chat)
    assert get_handler("download") is download.handle
    run_job(ctx_for(db))
    assert one(db, "SELECT status FROM jobs WHERE id = 1")[0] == "succeeded"
    assert one(db, "SELECT status, has_chat FROM source_streams") == ("processing", 1)
    assert {t for (t,) in all_rows(db, "SELECT job_type FROM jobs WHERE id > 1")} == {
        "detect_layout", "transcribe"}


def test_reimport_replaces_messages(db):
    assert download.import_chat(db, 1, CHAT) == 250
    assert download.import_chat(db, 1, CHAT) == 250
    assert one(db, "SELECT count(*) FROM chat_messages")[0] == 250


# --- parser & kata reaksi -----------------------------------------------------------------

def test_parse_emoji_runs_and_skips_system_messages():
    line = ('{"replayChatItemAction": {"actions": ['
            '{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {'
            '"message": {"runs": [{"text": "mantap "}, {"emoji": {"emojiId": "\U0001f602", '
            '"shortcuts": [":joy:"]}}, {"emoji": {"emojiId": "UCx/abc", "isCustomEmoji": true, '
            '"shortcuts": [":_kekw:"]}}]}, "authorName": {"simpleText": "a"}}}}},'
            '{"addChatItemAction": {"item": {"liveChatViewerEngagementMessageRenderer": {}}}},'
            '{"addLiveChatTickerItemAction": {}}], "videoOffsetTimeMsec": "-1500"}}')
    msgs = chat_replay.parse_line(line)
    assert msgs == [chat_replay.ChatMessage(-1500, "a", "mantap \U0001f602:_kekw:", "text")]
    assert chat_replay.parse_line("bukan json") == []
    assert chat_replay.parse_line('{"lain": 1}') == []


@pytest.mark.parametrize(("message", "expected"), [
    ("WKWK", True), ("lol bang", True), ("KEKW!!", True), ("ngakak \U0001f923", True),
    ("golongan", False), ("lolos", False), ("halo", False),
])
def test_reaction_matcher(message, expected):
    is_reaction = chat_replay.reaction_matcher(["wkwk", "lol", "kekw", "\U0001f923", "gg"])
    assert is_reaction(message) is expected
