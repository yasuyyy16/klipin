"""Subprocess (yt-dlp, FFmpeg) yang bisa dibatalkan dalam ≤ 10 detik (FR-023)."""

import os
import signal
import subprocess
import sys
import threading

GRACE_S = 5  # setelah sinyal berhenti, tunggu 5 detik lalu paksa


class JobCancelled(Exception):
    """Job dibatalkan Pengguna; status sudah `cancelled` di DB."""


def kill_tree(proc: subprocess.Popen) -> None:
    """Hentikan proses beserta anak-anaknya (mis. ffmpeg yang dijalankan yt-dlp)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(GRACE_S)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_cancellable(args: list[str], cancel: threading.Event, **popen_kwargs) -> int:
    """Jalankan perintah; jika `cancel` di-set, hentikan pohon prosesnya lalu JobCancelled."""
    if sys.platform != "win32":
        popen_kwargs.setdefault("start_new_session", True)  # agar killpg kena anak-anaknya
    proc = subprocess.Popen(args, **popen_kwargs)
    while True:
        try:
            return proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if cancel.is_set():
                kill_tree(proc)
                raise JobCancelled from None
