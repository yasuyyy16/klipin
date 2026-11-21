"""T-032: filtergraph preset statis → 1080×1920 tanpa bar hitam. TC-018 + snapshot per preset."""

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from klipin.layout.regions import Region
from klipin.media import ffmpeg, probe

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GAMING = FIXTURES / "gaming_facecam_30s.mp4"
PODCAST = FIXTURES / "podcast_two_faces_30s.mp4"
SRC_W, SRC_H = 960, 540


def truth_regions(name: str) -> list[Region]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [Region(r["role"], r["x"], r["y"], r["w"], r["h"], None) for r in data["regions"]]


GAMING_REGIONS = [*truth_regions("gaming_facecam_30s.regions.json"),
                  Region("content", 0.0, 0.0, 0.65, 1.0, None)]


def source_frame(src: Path, at_ms: int, tmp: Path) -> np.ndarray:
    out = tmp / f"src_{src.stem}_{at_ms}.png"
    subprocess.run([probe.ffmpeg_bin(), "-loglevel", "error", "-y", "-ss", f"{at_ms / 1000:.3f}",
                    "-i", str(src), "-frames:v", "1", str(out)], check=True)
    return cv2.imread(str(out))


def expected(src_frame: np.ndarray, plan: ffmpeg.LayoutPlan) -> np.ndarray:
    panels = [cv2.resize(src_frame[b.y:b.y + b.h, b.x:b.x + b.w], (ffmpeg.OUT_W, h),
                         interpolation=cv2.INTER_LANCZOS4) for b, h in plan.panels]
    return np.vstack(panels)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR pada skala 1/4: menghapus beda interpolasi lanczos FFmpeg (YUV) vs OpenCV (RGB)
    saat panel kecil di-upscale besar, tetapi tetap peka terhadap posisi crop."""
    size = (a.shape[1] // 4, a.shape[0] // 4)
    small = [cv2.resize(x, size, interpolation=cv2.INTER_AREA) for x in (a, b)]
    return float(cv2.PSNR(*small))


def assert_no_black_bars(img: np.ndarray) -> None:
    """Tepi kanvas dan sambungan panel tidak boleh berupa pita hitam penuh."""
    strips = {"atas": img[:6], "bawah": img[-6:], "kiri": img[:, :6], "kanan": img[:, -6:]}
    for name, strip in strips.items():
        black = (strip.max(axis=2) <= 16).mean()
        assert black < 0.9, f"pita hitam di tepi {name} ({black:.0%})"


@pytest.mark.parametrize(("preset", "src", "regions", "params"), [
    ("gaming", GAMING, GAMING_REGIONS, {"cam_height_pct": 35}),
    ("center_crop", GAMING, [], {}),
    ("split_two", PODCAST, truth_regions("podcast_two_faces_30s.regions.json"), {"split_pct": 50}),
    ("custom", GAMING, [GAMING_REGIONS[1], GAMING_REGIONS[0]], {}),  # konten atas, cam bawah
    ("custom", GAMING, [GAMING_REGIONS[0]], {}),
])
def test_snapshot_matches_expected_crop(tmp_path, home, preset, src, regions, params):
    plan = ffmpeg.plan_layout(preset, regions, SRC_W, SRC_H, params)
    assert plan.preset == preset and plan.fallback_reason is None
    assert sum(h for _, h in plan.panels) == ffmpeg.OUT_H
    out = ffmpeg.render_frame(src, 5000, plan, tmp_path / f"{preset}.png")
    img = cv2.imread(str(out))
    assert img.shape == (ffmpeg.OUT_H, ffmpeg.OUT_W, 3)
    src_frame = source_frame(src, 5000, tmp_path)
    good = psnr(img, expected(src_frame, plan))
    assert good >= 30
    # kontrol: crop yang digeser 10% lebar sumber harus jelas lebih buruk
    shifted = ffmpeg.LayoutPlan(plan.preset, plan.filter, [
        (ffmpeg.Box(min(b.x + 96, SRC_W - b.w) if b.x + b.w + 96 <= SRC_W else max(0, b.x - 96),
                    b.y, b.w, b.h), h) for b, h in plan.panels])
    assert psnr(img, expected(src_frame, shifted)) < good - 5
    assert_no_black_bars(img)


def test_tc018_gaming_mp4_cam_on_top_without_black_bars(tmp_path, home):
    plan = ffmpeg.plan_layout("gaming", GAMING_REGIONS, SRC_W, SRC_H, {"cam_height_pct": 35})
    out = tmp_path / "klip_gaming.mp4"
    subprocess.run([probe.ffmpeg_bin(), "-loglevel", "error", "-y", "-ss", "4", "-t", "2",
                    "-i", str(GAMING), "-filter_complex", plan.filter, "-map", "[vout]",
                    "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-r", "30",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    info = json.loads(subprocess.run(
        [probe.ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(out)], capture_output=True, text=True,
        check=True).stdout)["streams"][0]
    assert (info["width"], info["height"]) == (1080, 1920)

    frame = source_frame(out, 1000, tmp_path)
    exp = expected(source_frame(GAMING, 5000, tmp_path), plan)
    top = round(1920 * 0.35 / 2) * 2
    assert top == plan.panels[0][1] == 672
    # area 0–35% berisi crop cam (dibandingkan dengan crop facecam sumber yang di-scale)
    assert psnr(frame[:top], exp[:top]) >= 25
    assert psnr(frame[top:], exp[top:]) >= 25
    assert_no_black_bars(frame)


def test_cover_crop_keeps_aspect_and_stays_inside():
    box = ffmpeg.cover_crop((0.65, 0.525926, 0.333333, 0.444444), 960, 540, 1080, 672)
    assert box.w % 2 == 0 and box.h % 2 == 0 and box.x % 2 == 0 and box.y % 2 == 0
    assert abs(box.w / box.h - 1080 / 672) < 0.02
    assert box.x >= 624 and box.x + box.w <= 944 and box.y >= 284 and box.y + box.h <= 524
    full = ffmpeg.cover_crop((0, 0, 1, 1), 960, 540, 1080, 1920)
    assert (full.w, full.h) == (304, 540) and full.x == 328  # tengah 9:16
    edge = ffmpeg.cover_crop((0.9, 0.0, 0.1, 1.0), 960, 540, 1080, 1920)
    assert edge.x + edge.w <= 960


def test_missing_regions_fall_back_to_center_crop():
    plan = ffmpeg.plan_layout("gaming", [], SRC_W, SRC_H)
    assert plan.preset == "center_crop"
    assert plan.fallback_reason == "Region cam/konten belum ada"
    assert ffmpeg.plan_layout("custom", [], SRC_W, SRC_H).fallback_reason
    with pytest.raises(ValueError):
        ffmpeg.plan_layout("irl", [], SRC_W, SRC_H)


def test_filter_graph_shape():
    plan = ffmpeg.plan_layout("gaming", GAMING_REGIONS, SRC_W, SRC_H)
    assert plan.filter.startswith("[0:v]split=2[s0][s1];")
    assert plan.filter.endswith("[p0][p1]vstack=inputs=2[vout]")
    assert "pad" not in plan.filter  # cover, bukan letterbox
    single = ffmpeg.plan_layout("center_crop", [], SRC_W, SRC_H).filter
    assert single == "[0:v]crop=304:540:328:0,scale=1080:1920:flags=lanczos,setsar=1[vout]"
