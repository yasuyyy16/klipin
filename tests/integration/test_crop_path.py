"""T-033: jalur crop dinamis `irl` & `podcast` (wajah asli 5 fps + FFmpeg sendcmd). TC-019."""

import itertools
import subprocess
from pathlib import Path

import cv2
import pytest

from klipin.layout import crop_path as cp
from klipin.layout.face_detect import Face, FaceDetector
from klipin.media import probe

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
IRL = FIXTURES / "irl_moving_face_30s.mp4"
PODCAST = FIXTURES / "podcast_two_faces_30s.mp4"
SRC_W, SRC_H = 960, 540


@pytest.fixture(scope="module")
def detector():
    return FaceDetector()


@pytest.fixture(scope="module")
def irl_samples(detector):
    return cp.sample_faces(IRL, 0, 30_000, detector.detect)


@pytest.fixture(scope="module")
def podcast_samples(detector):
    return cp.sample_faces(PODCAST, 0, 10_000, detector.detect)


def test_sampling_is_5_fps_over_clip(irl_samples):
    times = [t for t, _ in irl_samples]
    assert times[:3] == [0, 200, 400]
    assert 145 <= len(times) <= 151
    assert sum(bool(f) for _, f in irl_samples) >= 0.9 * len(irl_samples)


def test_irl_follows_face_without_shaking(irl_samples):
    path = cp.irl_path(irl_samples, SRC_W, SRC_H, max_pan_pct_per_s=5)
    assert (path.crop_w, path.crop_h) == (304, 540)
    xs = dict(path.points)
    per_second = [xs[t] for t in range(0, 30_001, 1000) if t in xs]
    assert len(per_second) >= 29
    jumps = [abs(b - a) for a, b in itertools.pairwise(per_second)]
    assert max(jumps) <= 0.05 * SRC_W + 1  # simpangan antar-detik ≤ 5% lebar
    assert all(0 <= x <= SRC_W - path.crop_w for _, x in path.points)
    # tetap mengikuti wajah: pusat crop rata-rata dekat pusat wajah
    errors = [abs(xs[t] + path.crop_w / 2 - max(f, key=lambda f: f.area).cx * SRC_W)
              for t, f in irl_samples if f]
    assert sum(errors) / len(errors) < 0.1 * SRC_W


def test_tc019_podcast_switch_at_most_once_per_1_5_s(podcast_samples):
    turns = [cp.Turn(t, t + 500, "S1" if (t // 500) % 2 == 0 else "S2")
             for t in range(0, 10_000, 500)]
    path = cp.podcast_path(podcast_samples, turns, SRC_W, SRC_H, switch_hold_ms=1500)
    switches = cp.cuts(path, min_jump_px=path.crop_w // 2)
    assert switches, "crop harus tetap berpindah ke pembicara lain"
    gaps = [b - a for a, b in zip([0, *switches], switches, strict=False)]
    assert min(gaps) >= 1500


def test_podcast_follows_active_speaker(podcast_samples):
    # Fixture: kiri terdengar 0–5 dtk, kanan 5–10 dtk
    turns = [cp.Turn(0, 5000, "S1"), cp.Turn(5000, 10_000, "S2")]
    path = cp.podcast_path(podcast_samples, turns, SRC_W, SRC_H)
    center = {t: x + path.crop_w / 2 for t, x in path.points}
    assert all(center[t] < SRC_W / 2 for t in center if t < 5000)
    assert all(center[t] > SRC_W / 2 for t in center if t >= 5000)
    assert cp.cuts(path, path.crop_w // 2) == [5000]
    # pemetaan eksplisit membalik sisi
    flipped = cp.podcast_path(podcast_samples, turns, SRC_W, SRC_H,
                              speaker_faces={"S1": 1, "S2": 0})
    assert flipped.points[0][1] + flipped.crop_w / 2 > SRC_W / 2


def test_sendcmd_render_matches_path(irl_samples, tmp_path):
    path = cp.irl_path(irl_samples, SRC_W, SRC_H)
    cmd = tmp_path / "crop cmds.txt"  # spasi & huruf drive: uji escaping path di filter
    cmd.write_text(cp.sendcmd_text(path, 3000), encoding="utf-8")
    out = tmp_path / "irl.mp4"
    subprocess.run([probe.ffmpeg_bin(), "-loglevel", "error", "-y", "-t", "3", "-i", str(IRL),
                    "-filter_complex", cp.filter_for_path(path, cmd), "-map", "[vout]",
                    "-c:v", "libx264", "-preset", "veryfast", "-r", "30", "-pix_fmt", "yuv420p",
                    str(out)], check=True)
    cap = cv2.VideoCapture(str(out))
    assert (cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == (1080, 1920)
    cap.set(cv2.CAP_PROP_POS_MSEC, 2000)
    ok, frame = cap.read()
    assert ok
    src = cv2.VideoCapture(str(IRL))
    src.set(cv2.CAP_PROP_POS_MSEC, 2000)
    _, sframe = src.read()
    x = round(path.x_at(2000) / 2) * 2
    exp = cv2.resize(sframe[:, x:x + path.crop_w], (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
    small = [cv2.resize(f, (270, 480), interpolation=cv2.INTER_AREA) for f in (frame, exp)]
    assert cv2.PSNR(*small) >= 25
    wrong = cv2.resize(sframe[:, :path.crop_w], (1080, 1920))
    assert cv2.PSNR(small[0], cv2.resize(wrong, (270, 480), interpolation=cv2.INTER_AREA)) < 20


def test_sendcmd_text_interpolates_or_cuts():
    path = cp.CropPath(304, 540, [(0, 0), (1000, 100)])
    smooth = cp.sendcmd_text(path, 1000, fps=10).splitlines()
    assert smooth[0] == "0.0000 crop x 0;" and smooth[5] == "0.5000 crop x 50;"
    hard = cp.sendcmd_text(path, 1000, fps=10, hard_cuts=True).splitlines()
    assert hard[5] == "0.5000 crop x 0;"


def test_crop_size_and_no_faces():
    assert cp.crop_size(1920, 1080) == (608, 1080)
    assert cp.crop_size(1080, 1920) == (1080, 1920)
    empty = [(t, []) for t in range(0, 2000, 200)]
    path = cp.irl_path(empty, SRC_W, SRC_H)
    assert {x for _, x in path.points} == {328}  # tengah
    assert cp.irl_path([], SRC_W, SRC_H).points == [(0, 328)]


def test_single_face_sample_keeps_tracks():
    left, right = Face(0.2, 0.3, 0.1, 0.2, 0.9), Face(0.7, 0.3, 0.1, 0.2, 0.9)
    samples = [(0, [left, right]), (200, [right]), (400, [left, right])]
    path = cp.podcast_path(samples, [cp.Turn(0, 1000, "S2")], SRC_W, SRC_H,
                           speaker_faces={"S2": 1})
    assert all(x + path.crop_w / 2 > SRC_W / 2 for _, x in path.points)
