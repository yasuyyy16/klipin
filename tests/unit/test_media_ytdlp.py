"""T-021: media/ytdlp.py — inspect dari respons yt-dlp tersimpan, unduh fixture lokal + lanjutan."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest
from yt_dlp.utils import DownloadError

from klipin.media import ytdlp
from klipin.worker.process import JobCancelled

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAVED = FIXTURES / "ytdlp"
VIDEO = FIXTURES / "no_audio_10s.mp4"


def saved(name: str) -> dict:
    return json.loads((SAVED / name).read_text(encoding="utf-8"))


def fake_ydl(info: dict | None = None, error: str | None = None):
    """Pengganti YoutubeDL yang mengembalikan respons tersimpan tanpa jaringan."""

    class FakeYDL:
        opts: ClassVar[dict] = {}

        def __init__(self, opts):
            FakeYDL.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            assert download is False
            if error:
                raise DownloadError(error)
            return info

    return FakeYDL


# --- validasi URL -------------------------------------------------------------------------

@pytest.mark.parametrize(("url", "platform"), [
    ("https://www.youtube.com/watch?v=abc123XYZ00", "youtube"),
    ("https://youtu.be/abc123XYZ00", "youtube"),
    ("https://m.youtube.com/live/abc123XYZ00", "youtube"),
    ("  https://kick.com/namastreamer/videos/01a0251f-ef48-702d-9289-d66922da0e84 ", "kick"),
    ("https://www.kick.com/namastreamer", "kick"),
])
def test_platform_of_supported(url, platform):
    assert ytdlp.platform_of(url) == platform


@pytest.mark.parametrize("url", [
    "https://vimeo.com/12345",
    "https://youtube.com.evil.example/watch?v=x",
    "ftp://youtube.com/watch?v=x",
    "file:///C:/video.mp4",
    "bukan url",
    "",
    "http://[::1",
])
def test_platform_of_rejects(url):
    with pytest.raises(ytdlp.UrlNotSupportedError) as e:
        ytdlp.platform_of(url)
    assert str(e.value) == "URL tidak dikenali. Gunakan link VOD YouTube atau Kick."


# --- inspect ------------------------------------------------------------------------------

def test_inspect_youtube_vod_with_chat_replay():
    ydl = fake_ydl(saved("youtube_vod_chat.json"))
    r = ytdlp.inspect("https://www.youtube.com/watch?v=abc123XYZ00", ydl_cls=ydl)
    assert r.platform == "youtube"
    assert r.external_video_id == "abc123XYZ00"
    assert r.title == "Main horor sampai pagi"
    assert (r.channel_external_id, r.channel_name) == ("UCabcdefghijklmnopqrstuv", "NamaStreamer")
    assert r.duration_ms == 10_845_000
    assert r.is_live is False
    assert r.has_chat_replay is True
    assert r.estimated_size_bytes == 5962502134 + 175560000
    # opsi yt-dlp sesuai INT-01
    assert ydl.opts["skip_download"] is True
    assert ydl.opts["format"] == "bv*[height<=1080]+ba/b[height<=1080]"
    assert ydl.opts["noplaylist"] is True
    assert (ydl.opts["retries"], ydl.opts["fragment_retries"]) == (10, 10)


def test_inspect_youtube_live():
    r = ytdlp.inspect("https://www.youtube.com/watch?v=liveNOW1234",
                      ydl_cls=fake_ydl(saved("youtube_live.json")))
    assert r.is_live is True
    assert r.live_status == "is_live"
    assert r.duration_ms is None
    assert r.has_chat_replay is False


def test_inspect_kick_vod_size_from_bitrate():
    info = saved("kick_vod.json")
    r = ytdlp.inspect(info["webpage_url"], ydl_cls=fake_ydl(info))
    assert r.platform == "kick"
    assert r.external_video_id == "01a0251f-ef48-702d-9289-d66922da0e84"
    assert r.channel_external_id == "668"
    assert r.has_chat_replay is False  # VOD Kick tanpa chat (INT-03)
    assert r.estimated_size_bytes == 8000 * 1000 // 8 * 42250


def test_inspect_size_unknown_is_none():
    info = saved("youtube_vod_chat.json")
    del info["requested_formats"][1]["filesize_approx"]
    info["requested_formats"][1].pop("tbr")
    r = ytdlp.inspect(info["webpage_url"], ydl_cls=fake_ydl(info))
    assert r.estimated_size_bytes is None


def test_inspect_rejects_playlist_and_wrong_extractor():
    playlist = {"_type": "playlist", "id": "UCx", "title": "Kanal", "extractor_key": "YoutubeTab"}
    with pytest.raises(ytdlp.UrlNotSupportedError):
        ytdlp.inspect("https://www.youtube.com/@namastreamer", ydl_cls=fake_ydl(playlist))
    generic = {**saved("youtube_vod_chat.json"), "extractor_key": "Generic"}
    with pytest.raises(ytdlp.UrlNotSupportedError):
        ytdlp.inspect("https://www.youtube.com/watch?v=x", ydl_cls=fake_ydl(generic))


def test_inspect_unsupported_url_from_ytdlp():
    ydl = fake_ydl(error="ERROR: Unsupported URL: https://www.youtube.com/about")
    with pytest.raises(ytdlp.UrlNotSupportedError):
        ytdlp.inspect("https://www.youtube.com/about", ydl_cls=ydl)


def test_inspect_extraction_error_suggests_update():
    ydl = fake_ydl(error="ERROR: [youtube] abc: Sign in to confirm you're not a bot")
    with pytest.raises(ytdlp.YtdlpError) as e:
        ytdlp.inspect("https://www.youtube.com/watch?v=abc", ydl_cls=ydl)
    assert "Perbarui yt-dlp" in str(e.value)
    assert "not a bot" in e.value.detail


# --- unduh (yt-dlp sungguhan, server HTTP lokal dengan dukungan Range) --------------------

class _RangeServer:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.ranges: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/video.mp4":
                    self.send_error(404)
                    return
                rng = self.headers.get("Range")
                outer.ranges.append(rng)
                data, status = outer.payload, 200
                if rng:
                    start = int(rng.removeprefix("bytes=").split("-")[0])
                    data, status = outer.payload[start:], 206
                self.send_response(status)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                if status == 206:
                    total = len(outer.payload)
                    self.send_header("Content-Range", f"bytes {total - len(data)}-{total - 1}/{total}")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, args=(0.02,),
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    with _RangeServer(VIDEO.read_bytes()) as s:
        yield s


def local_info(base_url: str, path: str = "/video.mp4") -> dict:
    """Info dict yt-dlp tersimpan yang format-nya menunjuk ke fixture lokal."""
    return {
        "id": "fixture01", "title": "Fixture lokal", "extractor": "youtube",
        "extractor_key": "Youtube", "webpage_url": f"{base_url}{path}",
        "duration": 10,
        "formats": [
            {"format_id": "2160", "url": f"{base_url}/tidak-boleh.mp4", "ext": "mp4",
             "width": 3840, "height": 2160, "vcodec": "avc1", "acodec": "mp4a",
             "protocol": "http"},
            {"format_id": "540", "url": f"{base_url}{path}", "ext": "mp4", "width": 960,
             "height": 540, "fps": 30, "vcodec": "avc1", "acodec": "mp4a", "protocol": "http"},
        ],
    }


def test_download_fixture_selects_max_1080p(server, tmp_path):
    seen: list[int] = []
    r = ytdlp.download_vod(server.url, tmp_path, info=local_info(server.url),
                           on_progress=seen.append)
    assert r.path == tmp_path / "source.mp4"
    assert r.path.read_bytes() == server.payload
    assert (r.width, r.height, r.fps) == (960, 540, 30.0)
    assert server.ranges == [None]  # format 2160p tidak pernah diminta
    assert seen == sorted(seen)
    assert seen[-1] == 100


def test_download_resumes_partial_file(server, tmp_path):
    half = len(server.payload) // 2
    (tmp_path / "source.mp4.part").write_bytes(server.payload[:half])
    r = ytdlp.download_vod(server.url, tmp_path, info=local_info(server.url))
    assert server.ranges == [f"bytes={half}-"]
    assert r.path.read_bytes() == server.payload
    assert not (tmp_path / "source.mp4.part").exists()


def test_download_cancel_raises_job_cancelled(server, tmp_path):
    with pytest.raises(JobCancelled):
        ytdlp.download_vod(server.url, tmp_path, info=local_info(server.url),
                           should_cancel=lambda: True)
    assert not (tmp_path / "source.mp4").exists()


def test_download_http_error_is_ytdlp_error(server, tmp_path):
    with pytest.raises(ytdlp.YtdlpError) as e:
        ytdlp.download_vod(server.url, tmp_path, info=local_info(server.url, "/hilang.mp4"))
    assert "404" in e.value.detail


# --- chat replay (INT-02) -----------------------------------------------------------------

class _ChatYDL:
    """YoutubeDL palsu: menulis file live_chat seperti yt-dlp (`chat.live_chat.json`)."""

    opts: ClassVar[dict] = {}
    has_chat = True

    def __init__(self, opts):
        _ChatYDL.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        if not _ChatYDL.has_chat:
            return {"id": "x", "requested_subtitles": None}
        path = Path(self.opts["outtmpl"]["default"].replace("%(ext)s", "live_chat.json"))
        path.write_text('{"replayChatItemAction": {}}\n', encoding="utf-8")
        return {"id": "x", "requested_subtitles": {"live_chat": {"filepath": str(path)}}}


def test_download_live_chat_writes_chat_json(tmp_path):
    _ChatYDL.has_chat = True
    path = ytdlp.download_live_chat("https://www.youtube.com/watch?v=x", tmp_path,
                                    ydl_cls=_ChatYDL)
    assert path == tmp_path / "chat.json" and path.is_file()
    assert not (tmp_path / "chat.live_chat.json").exists()
    opts = _ChatYDL.opts
    assert (opts["skip_download"], opts["writesubtitles"], opts["subtitleslangs"]) == (
        True, True, ["live_chat"])


def test_download_live_chat_none_without_replay(tmp_path):
    _ChatYDL.has_chat = False
    assert ytdlp.download_live_chat("https://www.youtube.com/watch?v=x", tmp_path,
                                    ydl_cls=_ChatYDL) is None
