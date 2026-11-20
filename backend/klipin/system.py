"""Pemeliharaan sistem: perbarui yt-dlp (04-arsitektur.md §8.4)."""

import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version

import structlog

from klipin.config import ROOT_DIR, get_config

log = structlog.get_logger(__name__)
UPDATE_TIMEOUT_S = 180
RESTART_NOTE = "Mulai ulang Klipin agar versi baru dipakai."


class UpdateError(Exception):
    """Pembaruan gagal; pesan untuk Pengguna, detail teknis di log."""


def ytdlp_version() -> str | None:
    try:
        return version("yt-dlp")
    except PackageNotFoundError:
        return None


def update_ytdlp() -> dict:
    before = ytdlp_version()
    if get_config().klipin_providers == "fake":
        return {"updated": False, "version_before": before, "version_after": before,
                "message": "Mode uji (KLIPIN_PROVIDERS=fake): yt-dlp tidak diperbarui."}
    uv = shutil.which("uv")
    if uv is None:
        raise UpdateError("uv tidak ditemukan. Pasang uv lalu coba lagi.")
    # `uv run` menyelaraskan venv dengan uv.lock, jadi versi baru harus masuk ke lock.
    # --no-install-project: klipin.exe sedang dipakai proses ini (terkunci di Windows).
    for args in ([uv, "lock", "--upgrade-package", "yt-dlp"],
                 [uv, "sync", "--no-install-project", "--inexact"]):
        try:
            result = subprocess.run(args, cwd=ROOT_DIR, capture_output=True, text=True,
                                    timeout=UPDATE_TIMEOUT_S, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.error("update yt-dlp gagal", cmd=args[1], error=str(exc))
            raise UpdateError("Gagal memperbarui yt-dlp. Detail ada di log.") from exc
        if result.returncode != 0:
            log.error("update yt-dlp gagal", cmd=args[1], stderr=result.stderr[-2000:])
            raise UpdateError("Gagal memperbarui yt-dlp. Periksa koneksi internet; detail ada di log.")
    after = ytdlp_version()
    updated = after != before
    message = f"yt-dlp diperbarui ke {after}. {RESTART_NOTE}" if updated \
        else f"yt-dlp sudah versi terbaru ({after})."
    log.info("update yt-dlp", before=before, after=after)
    return {"updated": updated, "version_before": before, "version_after": after,
            "message": message}
