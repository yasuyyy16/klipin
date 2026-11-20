import socket

import pytest

from klipin import doctor

VERSION = "ffmpeg version 6.1.1 Copyright (c) 2000-2023 the FFmpeg developers\n"
ENCODERS = " V....D libx264              libx264 H.264 / AVC\n V....D libx265  x265\n"
FILTERS_WITH_ASS = (
    " ... ass               V->V       Render ASS subtitles\n"
    " ... subtitles         V->V       Render text subtitles\n"
)
FILTERS_NO_ASS = " ... scale             V->V       Scale the input video size\n"


def fake_ffmpeg(monkeypatch, version=VERSION, encoders=ENCODERS, filters=FILTERS_WITH_ASS):
    outputs = {"-version": version, "-encoders": encoders, "-filters": filters}
    monkeypatch.setattr(doctor, "_run", lambda args: outputs[args[-1]])


def by_name(checks):
    return {c.name: c for c in checks}


def test_full_ffmpeg_green(monkeypatch):
    fake_ffmpeg(monkeypatch)
    checks = by_name(doctor.check_ffmpeg("ffmpeg"))
    assert all(c.ok for c in checks.values())
    assert checks["FFmpeg"].detail == "6.1"


def test_ffmpeg_without_libass_red(monkeypatch):
    fake_ffmpeg(monkeypatch, filters=FILTERS_NO_ASS)
    checks = by_name(doctor.check_ffmpeg("ffmpeg"))
    assert checks["FFmpeg libass"].ok is False
    assert checks["FFmpeg libx264"].ok is True


def test_ffmpeg_without_libx264_red(monkeypatch):
    fake_ffmpeg(monkeypatch, encoders=" V....D libopenh264  OpenH264\n")
    assert by_name(doctor.check_ffmpeg("ffmpeg"))["FFmpeg libx264"].ok is False


def test_old_ffmpeg_red(monkeypatch):
    fake_ffmpeg(monkeypatch, version="ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright\n")
    assert by_name(doctor.check_ffmpeg("ffmpeg"))["FFmpeg"].ok is False


def test_missing_ffmpeg_all_red():
    assert not any(c.ok for c in doctor.check_ffmpeg(None))


def test_port_in_use_red():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert doctor.check_port(["127.0.0.1"], port).ok is False


def test_free_port_green():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert doctor.check_port(["127.0.0.1"], port).ok is True


def test_sqlite_and_python_green():
    assert doctor.check_sqlite().ok
    assert doctor.check_python().ok


@pytest.mark.parametrize("free_gb, ok", [(10, False), (80, True)])
def test_disk_threshold(monkeypatch, tmp_path, free_gb, ok):
    monkeypatch.setattr(
        doctor.shutil, "disk_usage", lambda p: type("U", (), {"free": free_gb * 1024**3})()
    )
    assert doctor.check_disk(tmp_path / "belum-ada").ok is ok
