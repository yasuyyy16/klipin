"""T-024: sumber media palsu mode fake (fixture, tanpa jaringan)."""

import pytest

from klipin.media import fake, ytdlp
from klipin.worker.process import JobCancelled


@pytest.mark.parametrize(("url", "vid", "platform", "live"), [
    ("https://www.youtube.com/watch?v=abc123&t=5", "abc123", "youtube", False),
    ("https://youtu.be/xyz789", "xyz789", "youtube", False),
    ("https://www.youtube.com/live/liveID1", "liveID1", "youtube", True),
    ("https://kick.com/nama/videos/01a0251f-ef48-702d-9289-d66922da0e84",
     "01a0251f-ef48-702d-9289-d66922da0e84", "kick", False),
    ("https://kick.com/namalive", "namalive", "kick", True),
])
def test_fake_inspect(url, vid, platform, live):
    r = fake.inspect(url)
    assert (r.external_video_id, r.platform, r.is_live) == (vid, platform, live)
    if live:
        assert r.duration_ms is None and r.estimated_size_bytes is None
    else:
        assert r.duration_ms == 30_000
        assert r.estimated_size_bytes == fake.VIDEO.stat().st_size
    assert r.has_chat_replay is (platform == "youtube" and not live)


def test_fake_inspect_still_rejects_foreign_url():
    with pytest.raises(ytdlp.UrlNotSupportedError):
        fake.inspect("https://vimeo.com/123")


def test_fake_download_copies_fixtures(tmp_path):
    seen = []
    r = fake.download_vod("https://youtu.be/x", tmp_path, on_progress=seen.append)
    assert r.path.read_bytes() == fake.VIDEO.read_bytes()
    assert seen[-1] == 100
    chat = fake.download_live_chat("https://youtu.be/x", tmp_path)
    assert chat.read_bytes() == fake.CHAT.read_bytes()


def test_fake_download_cancel(tmp_path):
    with pytest.raises(JobCancelled):
        fake.download_vod("https://youtu.be/x", tmp_path, should_cancel=lambda: True)
