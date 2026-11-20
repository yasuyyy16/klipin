"""Pemeriksaan prasyarat (`klipin doctor`, nanti juga `GET /system/health`)."""

import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from klipin.config import Config

MIN_PYTHON = (3, 11)
MIN_FFMPEG = (6, 0)
MIN_SQLITE = (3, 35, 0)
MIN_DISK_GB = 50


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=True).stdout


def check_python() -> Check:
    v = sys.version_info
    ok = v[:2] >= MIN_PYTHON
    return Check("Python", ok, f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (minimal 3.11)"))


def find_ffmpeg(cfg: Config) -> tuple[str | None, str | None]:
    if cfg.klipin_ffmpeg_path:
        ffmpeg = cfg.klipin_ffmpeg_path
        probe = ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe"))
        return (str(ffmpeg) if ffmpeg.is_file() else None, str(probe) if probe.is_file() else None)
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def check_ffmpeg(ffmpeg: str | None) -> list[Check]:
    names = ("FFmpeg", "FFmpeg libx264", "FFmpeg libass")
    if not ffmpeg:
        missing = "FFmpeg tidak ditemukan (pasang atau isi KLIPIN_FFMPEG_PATH)"
        return [Check(n, False, missing) for n in names]
    try:
        version_out = _run([ffmpeg, "-hide_banner", "-version"])
        encoders = _run([ffmpeg, "-hide_banner", "-encoders"])
        filters = _run([ffmpeg, "-hide_banner", "-filters"])
    except (OSError, subprocess.SubprocessError) as exc:
        return [Check(n, False, f"FFmpeg gagal dijalankan: {exc}") for n in names]

    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", version_out)
    if m:
        ver = (int(m.group(1)), int(m.group(2)))
        ver_ok = ver >= MIN_FFMPEG
        ver_detail = f"{ver[0]}.{ver[1]}" + ("" if ver_ok else " (minimal 6.0)")
    else:
        # Build git tanpa nomor versi: tidak bisa dipastikan, anggap gagal agar dicek manual.
        ver_ok, ver_detail = False, "versi tidak terbaca: " + version_out.splitlines()[0][:60]
    has_x264 = re.search(r"^\s*V\S*\s+libx264\s", encoders, re.MULTILINE) is not None
    has_ass = re.search(r"^\s*\S*\s+ass\s", filters, re.MULTILINE) is not None
    return [
        Check("FFmpeg", ver_ok, ver_detail),
        Check("FFmpeg libx264", has_x264, "ada" if has_x264 else "encoder libx264 tidak ada"),
        Check("FFmpeg libass", has_ass, "ada" if has_ass else "filter ass tidak ada (libass)"),
    ]


def check_ffprobe(ffprobe: str | None) -> Check:
    if not ffprobe:
        return Check("FFprobe", False, "FFprobe tidak ditemukan")
    try:
        first = _run([ffprobe, "-hide_banner", "-version"]).splitlines()[0]
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("FFprobe", False, f"FFprobe gagal dijalankan: {exc}")
    return Check("FFprobe", True, first.split(" Copyright")[0])


def check_ytdlp() -> Check:
    try:
        from yt_dlp.version import __version__
    except ImportError:
        return Check("yt-dlp", False, "yt-dlp tidak terpasang (jalankan `uv sync`)")
    return Check("yt-dlp", True, __version__)


def check_sqlite() -> Check:
    ver = sqlite3.sqlite_version_info
    try:
        sqlite3.connect(":memory:").execute("SELECT json_valid('{}')").fetchone()
        json1 = True
    except sqlite3.OperationalError:
        json1 = False
    ok = ver >= MIN_SQLITE and json1
    detail = sqlite3.sqlite_version + (", JSON1 ada" if json1 else ", JSON1 tidak ada")
    return Check("SQLite", ok, detail if ver >= MIN_SQLITE else detail + " (minimal 3.35)")


def check_keyring() -> Check:
    try:
        import keyring
        from keyring.backends import fail, null

        backend = keyring.get_keyring()
    except Exception as exc:  # noqa: BLE001 - backend keyring bisa melempar error jenis apa saja
        return Check("Keyring", False, f"keyring gagal dimuat: {exc}")
    usable = not isinstance(backend, (fail.Keyring, null.Keyring))
    name = type(backend).__module__ + "." + type(backend).__name__
    return Check("Keyring", usable, name if usable else f"tidak ada backend ({name}); pakai .env")


def check_disk(home: Path) -> Check:
    path = home
    while not path.exists():
        path = path.parent
    free_gb = shutil.disk_usage(path).free / 1024**3
    ok = free_gb >= MIN_DISK_GB
    detail = f"{free_gb:.1f} GB kosong di {path.anchor or path}"
    return Check("Ruang disk", ok, detail if ok else detail + f" (disarankan minimal {MIN_DISK_GB} GB)")


def check_port(hosts: list[str], port: int) -> Check:
    busy = []
    for host in hosts:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                busy.append(host)
    if busy:
        return Check(f"Port {port}", False, "dipakai di " + ", ".join(busy) + " (Klipin sudah jalan?)")
    return Check(f"Port {port}", True, "bebas di " + ", ".join(hosts))


def run_checks(cfg: Config, include_port: bool = True) -> list[Check]:
    ffmpeg, ffprobe = find_ffmpeg(cfg)
    checks = [
        check_python(),
        *check_ffmpeg(ffmpeg),
        check_ffprobe(ffprobe),
        check_ytdlp(),
        check_sqlite(),
        check_keyring(),
        check_disk(cfg.klipin_home),
    ]
    if include_port:
        checks.append(check_port(cfg.klipin_host, cfg.klipin_port))
    return checks


def print_report(checks: list[Check]) -> None:
    color = sys.stdout.isatty()
    if color and sys.platform == "win32":
        os.system("")  # mengaktifkan kode warna ANSI di console Windows lama
    width = max(len(c.name) for c in checks)
    for c in checks:
        status = "OK   " if c.ok else "GAGAL"
        if color:
            status = f"\033[{'32' if c.ok else '31'}m{status}\033[0m"
        print(f"{c.name:<{width}}  {status}  {c.detail}")
