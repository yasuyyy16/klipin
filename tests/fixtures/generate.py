"""Membuat ulang fixture uji (09-testing.md §5).

    uv run python tests/fixtures/generate.py
    uv run python tests/fixtures/generate.py --faces SASHA.webm RIMPAC.webm

Tanpa argumen: fixture sintetis dari generator FFmpeg (lavfi) dan Python.
Dengan --faces: juga fixture berwajah dari dua video domain publik Wikimedia Commons
(judul, SHA1, dan lisensi ada di FACE_SOURCES dan README.md).
"""

import argparse
import hashlib
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
    # MP4 tanpa faststart menaruh atom moov di akhir; dipotong 30% → "moov atom not found".
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
    react = ["wkwkwk", "awokawok", "KEKW", "anjir", "😂😂", "lmao", "wkwk", "🤣"]
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


# --- Fixture berwajah -------------------------------------------------------------------
# Sumber 1920x1080; segmen = potongan wawancara menghadap kamera (tanpa b-roll), hasil
# deteksi pergantian adegan FFmpeg (scdet) lalu dicek manual.
FACE_SOURCES = {
    "sasha": {
        "title": "File:Faces of Keen Sword - Tech Sgt Sasha Marceaux (1027106).webm",
        "sha1": "9c022062c6565af5681c6d5a1343ef2a57a0e83a",
        "segments": [(5.6, 10.3), (14.6, 19.8), (24.9, 30.8)],
    },
    "maryam": {
        "title": "File:Faces of RIMPAC Philippines.webm",
        "sha1": "bb6852df5f6f3a7aabe59c5171836117f3a06201",
        "segments": [(11.2, 19.2), (25.8, 29.2), (34.7, 42.4)],
    },
}
FACE_SECONDS = 30
OUT_W, OUT_H = 960, 540
# Facecam gaming: crop 480x360 di sekitar wajah Sasha, tampil 320x240 di pojok kanan bawah.
CAM_CROP = (480, 360, 420, 200)  # w, h, x, y pada sumber
CAM_BOX = (320, 240, OUT_W - 16 - 320, OUT_H - 16 - 240)  # w, h, x, y pada output


def verify_source(path: Path, sha1: str) -> None:
    digest = hashlib.sha1(path.read_bytes()).hexdigest()
    if digest != sha1:
        raise SystemExit(f"SHA1 {path.name} tidak cocok: {digest} (harus {sha1})")


def face_inputs(path: Path, segments: list[tuple[float, float]], first_index: int):
    """Input FFmpeg per segmen (diulang sampai >= FACE_SECONDS) + filter concat-nya."""
    args, labels, total, i = [], [], 0.0, 0
    while total < FACE_SECONDS:
        start, end = segments[i % len(segments)]
        args += ["-ss", f"{start}", "-t", f"{end - start:.3f}", "-i", str(path)]
        idx = first_index + i
        labels.append(f"[{idx}:v:0][{idx}:a:0]")
        total += end - start
        i += 1
    return args, "".join(labels) + f"concat=n={i}:v=1:a=1", i


def norm(w: int, h: int, x: int, y: int) -> dict:
    return {"x": round(x / OUT_W, 6), "y": round(y / OUT_H, 6),
            "w": round(w / OUT_W, 6), "h": round(h / OUT_H, 6)}


def write_regions(name: str, data: dict) -> None:
    path = HERE / f"{name}.regions.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_gaming(sasha: Path) -> None:
    inputs, concat, _ = face_inputs(sasha, FACE_SOURCES["sasha"]["segments"], 1)
    cw, ch, cx, cy = CAM_CROP
    bw, bh, bx, by = CAM_BOX
    ffmpeg(*game_video(FACE_SECONDS), *inputs, "-filter_complex",
           f"{concat}[fv][fa];[fv]fps={FPS},crop={cw}:{ch}:{cx}:{cy},scale={bw}:{bh}[cam];"
           f"[0:v][cam]overlay={bx}:{by}[v]",
           "-map", "[v]", "-map", "[fa]", "-t", str(FACE_SECONDS),
           "-c:a", "aac", "-b:a", "64k", *x264(HERE / "gaming_facecam_30s.mp4"))
    write_regions("gaming_facecam_30s", {
        "frame": {"width": OUT_W, "height": OUT_H},
        "note": "Ground truth Region Cam (format cam_regions, ternormalisasi 0-1). Posisi tetap "
                "selama 30 detik karena facecam ditempel generator.",
        "suggested_preset": "gaming",
        "regions": [{"role": "cam", **norm(bw, bh, bx, by)}],
    })


def make_podcast(sasha: Path, maryam: Path) -> None:
    a_in, a_concat, n = face_inputs(sasha, FACE_SOURCES["sasha"]["segments"], 0)
    b_in, b_concat, _ = face_inputs(maryam, FACE_SOURCES["maryam"]["segments"], n)
    half = OUT_W // 2
    # Pembicara bergantian tiap 5 detik: kiri (S1) lalu kanan (S2).
    turn = 5
    ffmpeg(*a_in, *b_in, "-filter_complex",
           f"{a_concat}[av][aa];{b_concat}[bv][ba];"
           f"[av]fps={FPS},crop=540:608:400:150,scale={half}:{OUT_H}[l];"
           f"[bv]fps={FPS},crop=764:860:1000:0,scale={half}:{OUT_H}[r];"
           f"[l][r]hstack[v];"
           f"[aa]volume='lt(mod(t,{2 * turn}),{turn})':eval=frame[a1];"
           f"[ba]volume='gte(mod(t,{2 * turn}),{turn})':eval=frame[a2];"
           f"[a1][a2]amix=inputs=2:normalize=0[a]",
           "-map", "[v]", "-map", "[a]", "-t", str(FACE_SECONDS),
           "-c:a", "aac", "-b:a", "64k", *x264(HERE / "podcast_two_faces_30s.mp4"))
    write_regions("podcast_two_faces_30s", {
        "frame": {"width": OUT_W, "height": OUT_H},
        "note": "face_a = panel kiri, face_b = panel kanan; speakers = siapa yang terdengar.",
        "suggested_preset": "podcast",
        "regions": [{"role": "face_a", **norm(half, OUT_H, 0, 0)},
                    {"role": "face_b", **norm(half, OUT_H, half, 0)}],
        "speakers": [{"start_ms": s * 1000, "end_ms": (s + turn) * 1000,
                      "speaker": "S1" if (s // turn) % 2 == 0 else "S2"}
                     for s in range(0, FACE_SECONDS, turn)],
    })


def make_irl(maryam: Path) -> None:
    inputs, concat, _ = face_inputs(maryam, FACE_SOURCES["maryam"]["segments"], 0)
    # Jendela 1280x720 bergeser di sumber, jadi wajah bergerak di output; batas x/y menjaga
    # wajah tetap di dalam bingkai dan subtitle tertanam (y >= ~880) di luar bingkai.
    ffmpeg(*inputs, "-filter_complex",
           f"{concat}[fv][fa];[fv]fps={FPS},"
           "crop=1280:720:x='510+130*sin(2*PI*t/12)':y='60+40*sin(2*PI*t/9)',"
           f"scale={OUT_W}:{OUT_H}[v]",
           "-map", "[v]", "-map", "[fa]", "-t", str(FACE_SECONDS),
           "-c:a", "aac", "-b:a", "64k", *x264(HERE / "irl_moving_face_30s.mp4"))


def make_faces(sasha: Path, maryam: Path) -> None:
    verify_source(sasha, FACE_SOURCES["sasha"]["sha1"])
    verify_source(maryam, FACE_SOURCES["maryam"]["sha1"])
    make_gaming(sasha)
    make_podcast(sasha, maryam)
    make_irl(maryam)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Buat ulang fixture uji Klipin")
    parser.add_argument("--faces", nargs=2, type=Path, metavar=("SASHA", "RIMPAC"),
                        help="video sumber wajah (lihat FACE_SOURCES)")
    parser.add_argument("--only-faces", action="store_true",
                        help="lewati fixture sintetis")
    args = parser.parse_args()
    if not args.only_faces:
        make_no_face()
        make_no_audio()
        make_corrupt()
        make_audio_scream()
        make_chat()
    if args.faces:
        make_faces(*args.faces)
    for p in sorted(HERE.iterdir()):
        if p.suffix in {".mp4", ".flac", ".jsonl"}:
            print(f"{p.name:32} {p.stat().st_size / 1024:8.0f} KB")
