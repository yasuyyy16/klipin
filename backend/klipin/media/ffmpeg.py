"""Filtergraph FFmpeg per Preset Layout statis → kanvas 1080×1920 tanpa bar hitam (FR-007).

Setiap panel memakai strategi *cover*: Region Cam (koordinat 0–1 relatif frame sumber)
dipotong lagi di tengahnya ke rasio panel tujuan, lalu di-scale tepat ke ukuran panel. Tidak ada
`pad`, jadi tidak ada bar hitam. Panel ditumpuk dengan `vstack`.

- `gaming`: `cam` di atas (`cam_height_pct`, default 35%), `content` di bawah.
- `split_two`: `face_a` di atas, `face_b` di bawah (`split_pct`, default 50%).
- `center_crop`: potongan tengah 9:16 dari seluruh frame.
- `custom`: 1 region → penuh; 2 region → ditumpuk sesuai urutan (`top_pct`, default 50%).
Region wajib yang tidak ada → jatuh ke `center_crop` (dicatat pemanggil lewat `LayoutPlan`).
Preset dinamis (`irl`, `podcast`) dibuat di T-033.
"""

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from klipin.media.probe import ffmpeg_bin

OUT_W, OUT_H = 1080, 1920
STATIC_PRESETS = {"gaming", "split_two", "center_crop", "custom"}


class RegionLike(Protocol):
    role: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Box:
    """Kotak dalam piksel sumber (bilangan bulat, genap agar aman untuk yuv420p)."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class LayoutPlan:
    preset: str  # preset yang benar-benar dipakai (bisa jatuh ke center_crop)
    filter: str  # filtergraph untuk -filter_complex, keluaran berlabel [vout]
    panels: list[tuple[Box, int]]  # (potongan sumber, tinggi panel) dari atas ke bawah
    fallback_reason: str | None = None


def _even(v: float) -> int:
    return max(2, round(v / 2) * 2)


def cover_crop(region: tuple[float, float, float, float], src_w: int, src_h: int,
               out_w: int, out_h: int) -> Box:
    """Potongan terbesar di tengah region yang rasionya sama dengan panel tujuan."""
    rx, ry, rw, rh = (region[0] * src_w, region[1] * src_h, region[2] * src_w, region[3] * src_h)
    target = out_w / out_h
    if rw / rh > target:  # region lebih lebar: potong kiri-kanan
        cw, ch = rh * target, rh
    else:  # region lebih tinggi: potong atas-bawah
        cw, ch = rw, rw / target
    w, h = min(_even(cw), src_w - src_w % 2), min(_even(ch), src_h - src_h % 2)
    # Offset genap: di yuv420p offset ganjil menggeser chroma setengah piksel.
    x = round((rx + (rw - w) / 2) / 2) * 2
    y = round((ry + (rh - h) / 2) / 2) * 2
    x = min(max(0, x), (src_w - w) // 2 * 2)
    y = min(max(0, y), (src_h - h) // 2 * 2)
    return Box(x, y, w, h)


def _heights(top_pct: float) -> tuple[int, int]:
    top = _even(OUT_H * top_pct / 100)
    return top, OUT_H - top


def _panel(label_in: str, box: Box, height: int, label_out: str) -> str:
    return (f"[{label_in}]crop={box.w}:{box.h}:{box.x}:{box.y},"
            f"scale={OUT_W}:{height}:flags=lanczos,setsar=1[{label_out}]")


def _graph(panels: list[tuple[Box, int]]) -> str:
    if len(panels) == 1:
        box, height = panels[0]
        return _panel("0:v", box, height, "vout")
    names = [f"p{i}" for i in range(len(panels))]
    split = f"[0:v]split={len(panels)}" + "".join(f"[s{i}]" for i in range(len(panels)))
    parts = [split] + [_panel(f"s{i}", box, h, names[i]) for i, (box, h) in enumerate(panels)]
    parts.append("".join(f"[{n}]" for n in names) + f"vstack=inputs={len(panels)}[vout]")
    return ";".join(parts)


def plan_layout(preset: str, regions: Sequence[RegionLike], src_w: int, src_h: int,
                params: Mapping[str, Any] | None = None) -> LayoutPlan:
    """Susun panel untuk preset statis. `regions` untuk `custom` dibaca sesuai urutan."""
    if preset not in STATIC_PRESETS:
        raise ValueError(f"preset {preset} bukan preset statis")
    params = params or {}
    by_role = {r.role: r for r in regions}

    def box(r: RegionLike, height: int) -> Box:
        return cover_crop((r.x, r.y, r.w, r.h), src_w, src_h, OUT_W, height)

    reason = None
    if preset == "gaming":
        if {"cam", "content"} <= by_role.keys():
            top, bottom = _heights(float(params.get("cam_height_pct", 35)))
            panels = [(box(by_role["cam"], top), top), (box(by_role["content"], bottom), bottom)]
            return LayoutPlan(preset, _graph(panels), panels)
        reason = "Region cam/konten belum ada"
    elif preset == "split_two":
        if {"face_a", "face_b"} <= by_role.keys():
            top, bottom = _heights(float(params.get("split_pct", 50)))
            panels = [(box(by_role["face_a"], top), top), (box(by_role["face_b"], bottom), bottom)]
            return LayoutPlan(preset, _graph(panels), panels)
        reason = "Region dua wajah belum ada"
    elif preset == "custom":
        chosen = list(regions)[:2]
        if len(chosen) == 1:
            panels = [(box(chosen[0], OUT_H), OUT_H)]
            return LayoutPlan(preset, _graph(panels), panels)
        if len(chosen) == 2:
            top, bottom = _heights(float(params.get("top_pct", 50)))
            panels = [(box(chosen[0], top), top), (box(chosen[1], bottom), bottom)]
            return LayoutPlan(preset, _graph(panels), panels)
        reason = "Region kustom belum digambar"

    full = cover_crop((0.0, 0.0, 1.0, 1.0), src_w, src_h, OUT_W, OUT_H)
    panels = [(full, OUT_H)]
    return LayoutPlan("center_crop", _graph(panels), panels,
                      None if preset == "center_crop" else reason)


def render_frame(src: Path, at_ms: int, plan: LayoutPlan, out_png: Path,
                 timeout_s: float = 60) -> Path:
    """Satu frame tata letak (snapshot/pratinjau cepat) ke PNG 1080×1920."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_ms / 1000:.3f}",
         "-i", str(src), "-filter_complex", plan.filter, "-map", "[vout]", "-frames:v", "1",
         str(out_png)], capture_output=True, text=True, timeout=timeout_s, check=False)
    if result.returncode != 0 or not out_png.is_file():
        raise RuntimeError(f"FFmpeg gagal membuat frame: {result.stderr.strip()[-300:]}")
    return out_png
