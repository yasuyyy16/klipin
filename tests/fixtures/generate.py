"""Membuat ulang fixture sintetis (09-testing.md Â§5). Jalankan: uv run python tests/fixtures/generate.py

Semua isi dibuat dari generator FFmpeg (lavfi) dan Python, tanpa materi pihak ketiga.
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SIZE = "960x540"
FPS = 30


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def game_video(seconds: int) -> list[str]:
    # Pola uji FFmpeg yang bergerak sebagai pengganti layar game, tanpa wajah.
    return ["-f", "lavfi", "-i", f"testsrc2=s={SIZE}:r={FPS}:d={seconds}"]


def x264(out: Path) -> list[str]:
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "34", "-pix_fmt", "yuv420p",
            "-threads", "1", str(out)]


def make_no_face() -> None:
    ffmpeg(*game_video(30),
           "-f", "lavfi", "-i", "sine=f=330:sample_rate=48000:d=30",
           "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "64k",
           *x264(HERE / "no_face_30s.mp4"))


def make_no_audio() -> None:
    ffmpeg(*game_video(10), "-an", *x264(HERE / "no_audio_10s.mp4"))


def make_corrupt() -> None:
    # MP4 tanpa faststart menaruh atom moov di akhir; dipotong 30% â†’ "moov atom not found".
    tmp = HERE / "_tmp_full.mp4"
    ffmpeg(*game_video(5), "-an", *x264(tmp))
    data = tmp.read_bytes()
    (HERE / "corrupt.mp4").write_bytes(data[: len(data) * 3 // 10])
    tmp.unlink()


def make_audio_scream() -> None:
    # 25 menit hening + semburan pink noise keras 3 detik di menit 10. Lantai hening dipilih
    # karena nada pelan apa pun membuat FLAC 6+ MB; untuk Sinyal Audio hasilnya setara.
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1500",
           "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:a=0.9:seed=7:r=16000",
           "-filter_complex",
           "[1]adelay=600000:all=1[s];[0][s]amix=inputs=2:normalize=0:duration=first",
           "-ac", "1", "-c:a", "flac", "-compression_level", "12",
           str(HERE / "audio_25min_scream_at_10.flac"))


def _text_item(msg_id: str, author: str, text: str, ts_usec: int) -> dict:
    return {"liveChatTextMessageRenderer": {
        "id": msg_id,
        "message": {"runs": [{"text": text}]},
        "authorName": {"simpleText": author},
        "authorExternalChannelId": f"UC{msg_id[-10:]:0>22}",
        "timestampUsec": str(ts_usec),
    }}


def make_chat() -> None:
    """Chat replay format yt-dlp `live_chat` (JSON-lines, satu replayChatItemAction per baris).

    20 menit; dasar 2 pesan per 10 detik; detik 600-610 berisi 10 pesan (5x median, TC-021).
    """
    rng = random.Random(1234)
    base_usec = 1_763_600_000_000_000  # 2025-11-20T00:53:20Z, waktu siaran fiktif
    normal = ["halo bang", "mantap", "lanjut", "gg", "itu tadi apa", "nice", "first time nonton"]
    react = ["wkwkwk", "awokawok", "KEKW", "anjir", "ðŸ˜‚ðŸ˜‚", "lmao", "wkwk", "ðŸ¤£"]
    events: list[tuple[int, dict]] = []
    n = 0
    for window in range(0, 1200, 10):
        count = 10 if window == 600 else 2
        for i in range(count):
            offset_ms = window * 1000 + i * (10_000 // count)
            pool = react if window == 600 else normal
            n += 1
            item = _text_item(f"msg{n:06d}", f"penonton{rng.randint(1, 300)}",
                              rng.choice(pool), base_usec + offset_ms * 1000)
            events.append((offset_ms, item))
    events.append((305_000, {"liveChatPaidMessageRenderer": {
        "id": "paid000001", "message": {"runs": [{"text": "semangat bang"}]},
        "authorName": {"simpleText": "donatur1"}, "purchaseAmountText": {"simpleText": "Rp20.000"},
        "timestampUsec": str(base_usec + 305_000_000)}}))
    events.append((905_000, {"liveChatMembershipItemRenderer": {
        "id": "member00001", "headerSubtext": {"runs": [{"text": "Welcome to the channel!"}]},
        "authorName": {"simpleText": "member1"},
        "timestampUsec": str(base_usec + 905_000_000)}}))
    events.sort(key=lambda e: e[0])

    with (HERE / "live_chat_spike.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for offset_ms, item in events:
            line = {"replayChatItemAction": {
                "actions": [{"addChatItemAction": {"item": item, "clientId": ""}}],
                "videoOffsetTimeMsec": str(offset_ms),
            }, "videoOffsetTimeMsec": str(offset_ms), "isLive": False}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    make_no_face()
    make_no_audio()
    make_corrupt()
    make_audio_scream()
    make_chat()
    for p in sorted(HERE.iterdir()):
        if p.suffix in {".mp4", ".flac", ".jsonl"}:
            print(f"{p.name:32} {p.stat().st_size / 1024:8.0f} KB")
