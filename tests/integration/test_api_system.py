"""T-020: GET /system/health, POST /system/update-ytdlp (tanpa jaringan sungguhan)."""

import subprocess

import pytest

from klipin import system
from klipin.config import get_config


def test_health_lists_checks_without_port(api, home):
    body = api.get("/api/v1/system/health").json()
    names = [c["name"] for c in body["checks"]]
    assert {"Python", "FFmpeg libass", "yt-dlp", "SQLite", "Keyring", "Ruang disk"} <= set(names)
    assert not any(n.startswith("Port") for n in names)
    assert body["ok"] == all(c["ok"] for c in body["checks"])
    assert body["backup_dir"] == str(home / "backups")


def test_update_ytdlp_fake_mode_does_nothing(api, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("tidak boleh dipanggil"))
    body = api.post("/api/v1/system/update-ytdlp").json()
    assert body["updated"] is False
    assert body["version_before"] == body["version_after"]


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    monkeypatch.setattr(system.shutil, "which", lambda name: "uv")


def test_update_ytdlp_runs_lock_then_sync(api, real_mode, monkeypatch):
    calls = []
    versions = iter(["2026.10.26", "2026.11.15"])
    monkeypatch.setattr(system, "ytdlp_version", lambda: next(versions))
    monkeypatch.setattr(system.subprocess, "run", lambda args, **kw: calls.append(args) or
                        subprocess.CompletedProcess(args, 0, "", ""))
    body = api.post("/api/v1/system/update-ytdlp").json()
    assert calls == [["uv", "lock", "--upgrade-package", "yt-dlp"],
                     ["uv", "sync", "--no-install-project", "--inexact"]]
    assert body["updated"] is True
    assert body["message"] == "yt-dlp diperbarui ke 2026.11.15. Mulai ulang Klipin agar versi baru dipakai."


def test_update_ytdlp_failure_is_502(api, real_mode, monkeypatch):
    monkeypatch.setattr(system.subprocess, "run", lambda args, **kw:
                        subprocess.CompletedProcess(args, 1, "", "network unreachable"))
    resp = api.post("/api/v1/system/update-ytdlp")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "UPSTREAM_ERROR"
    assert "network unreachable" not in resp.text  # detail teknis hanya di log
