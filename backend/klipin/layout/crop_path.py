"""Jalur crop dinamis 9:16 untuk preset `irl` dan `podcast` (FR-007, ADR-004).

Wajah disampel 5 fps hanya di rentang Klip. Hasilnya posisi kiri jendela crop (piksel
sumber) per sampel, lalu diinterpolasi per frame keluaran dan dikirim ke filter `crop` lewat
`sendcmd` (pan halus, bukan lompatan tiap 200 ms).

- `irl`: target = pusat wajah terbesar; dihaluskan median 1 detik, lalu kecepatan geser
  dibatasi `max_pan_pct_per_s` (default 5% lebar frame per detik).
- `podcast`: target = wajah pembicara aktif (giliran bicara dari diarization). Crop berpindah
  dengan potongan langsung, tetapi tidak lebih sering dari sekali per `switch_hold_ms` (1,5 dtk).
  Pemetaan pembicara → wajah: pembicara yang lebih dulu bicara ↔ wajah paling kiri (urutan
  posisi), kecuali `speaker_faces` diberikan.
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2

from klipin.layout.face_detect import Face
from klipin.worker.process import JobCancelled

SAMPLE_FPS = 5
OUTPUT_FPS = 30
SMOOTH_WINDOW = 5  # sampel (1 detik pada 5 fps)
FRAME_WIDTH = 960


@dataclass(frozen=True)
class Turn:
    start_ms: int
    end_ms: int
    speaker: str


@dataclass(frozen=True)
class CropPath:
    """`points`: (t_ms relatif awal Klip, x kiri jendela crop dalam piksel sumber)."""

    crop_w: int
    crop_h: int
    points: list[tuple[int, int]]

    def x_at(self, t_ms: float) -> float:
        pts = self.points
        if t_ms <= pts[0][0]:
            return pts[0][1]
        for (t0, x0), (t1, x1) in itertools.pairwise(pts):
            if t_ms <= t1:
                return x0 if t1 == t0 else x0 + (x1 - x0) * (t_ms - t0) / (t1 - t0)
        return pts[-1][1]


def crop_size(src_w: int, src_h: int) -> tuple[int, int]:
    """Jendela 9:16 terbesar (genap) di frame sumber."""
    if src_w / src_h > 9 / 16:
        return max(2, round(src_h * 9 / 16 / 2) * 2), src_h - src_h % 2
    return src_w - src_w % 2, max(2, round(src_w * 16 / 9 / 2) * 2)


def sample_faces(video: Path, start_ms: int, end_ms: int, detect: Callable,
                 should_cancel: Callable[[], bool] | None = None,
                 fps: int = SAMPLE_FPS) -> list[tuple[int, list[Face]]]:
    """Baca rentang Klip berurutan; deteksi wajah tiap 1/fps detik. t relatif awal Klip."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("Video sumber tidak bisa dibaca.")
    step = 1000 / fps
    out: list[tuple[int, list[Face]]] = []
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, start_ms)
        next_t = 0.0
        while next_t <= end_ms - start_ms:
            if should_cancel and should_cancel():
                raise JobCancelled
            if not cap.grab():
                break
            pos = cap.get(cv2.CAP_PROP_POS_MSEC) - start_ms
            if pos + 1 < next_t:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            h, w = frame.shape[:2]
            if w > FRAME_WIDTH:
                frame = cv2.resize(frame, (FRAME_WIDTH, round(h * FRAME_WIDTH / w)),
                                   interpolation=cv2.INTER_AREA)
            out.append((round(next_t), detect(frame)))
            next_t += step
    finally:
        cap.release()
    return out


def _left_for_center(cx: float, src_w: int, crop_w: int) -> float:
    return min(max(0.0, cx * src_w - crop_w / 2), src_w - crop_w)


def _median_smooth(values: list[float], window: int = SMOOTH_WINDOW) -> list[float]:
    half = window // 2
    return [median(values[max(0, i - half):i + half + 1]) for i in range(len(values))]


def irl_path(samples: Sequence[tuple[int, list[Face]]], src_w: int, src_h: int,
             max_pan_pct_per_s: float = 5.0) -> CropPath:
    crop_w, crop_h = crop_size(src_w, src_h)
    targets: list[float] = []
    last = 0.5
    for _, faces in samples:
        if faces:
            last = max(faces, key=lambda f: f.area).cx
        targets.append(last)  # tanpa wajah: tahan posisi terakhir
    if not samples:
        return CropPath(crop_w, crop_h, [(0, round(_left_for_center(0.5, src_w, crop_w)))])
    lefts = [_left_for_center(c, src_w, crop_w) for c in _median_smooth(targets)]
    max_px_per_ms = max_pan_pct_per_s / 100 * src_w / 1000
    x = lefts[0]
    points = [(samples[0][0], round(x))]
    for (t_prev, _), (t, _), target in zip(samples, samples[1:], lefts[1:], strict=False):
        limit = max_px_per_ms * (t - t_prev)
        x += max(-limit, min(limit, target - x))
        points.append((t, round(x)))
    return CropPath(crop_w, crop_h, points)


def _tracks(samples: Sequence[tuple[int, list[Face]]]) -> list[list[float]]:
    """Dua jalur wajah kiri/kanan (pusat x) per sampel; sampel kurang wajah menahan posisi."""
    left, right = 0.25, 0.75
    out_l, out_r = [], []
    for _, faces in samples:
        two = sorted(sorted(faces, key=lambda f: f.area, reverse=True)[:2], key=lambda f: f.cx)
        if len(two) == 2:
            left, right = two[0].cx, two[1].cx
        elif len(two) == 1:
            if abs(two[0].cx - left) <= abs(two[0].cx - right):
                left = two[0].cx
            else:
                right = two[0].cx
        out_l.append(left)
        out_r.append(right)
    return [_median_smooth(out_l), _median_smooth(out_r)]


def speaker_at(turns: Sequence[Turn], t_ms: int) -> str | None:
    for turn in turns:
        if turn.start_ms <= t_ms < turn.end_ms:
            return turn.speaker
    return None


def podcast_path(samples: Sequence[tuple[int, list[Face]]], turns: Sequence[Turn],
                 src_w: int, src_h: int, switch_hold_ms: int = 1500,
                 speaker_faces: dict[str, int] | None = None) -> CropPath:
    """`turns` relatif awal Klip. `speaker_faces`: label pembicara → 0 (kiri) / 1 (kanan)."""
    crop_w, crop_h = crop_size(src_w, src_h)
    if not samples:
        return CropPath(crop_w, crop_h, [(0, round(_left_for_center(0.5, src_w, crop_w)))])
    if speaker_faces is None:
        order = []
        for turn in sorted(turns, key=lambda t: t.start_ms):
            if turn.speaker not in order:
                order.append(turn.speaker)
        speaker_faces = {s: min(i, 1) for i, s in enumerate(order)}
    tracks = _tracks(samples)

    current: int | None = None
    switched_at = -switch_hold_ms
    points: list[tuple[int, int]] = []
    for i, (t, _) in enumerate(samples):
        speaker = speaker_at(turns, t)
        wanted = speaker_faces.get(speaker) if speaker else None
        if current is None:
            current = 0 if wanted is None else wanted
            switched_at = t
        elif wanted is not None and wanted != current and t - switched_at >= switch_hold_ms:
            current, switched_at = wanted, t
        points.append((t, round(_left_for_center(tracks[current][i], src_w, crop_w))))
    return CropPath(crop_w, crop_h, points)


def cuts(path: CropPath, min_jump_px: int) -> list[int]:
    """Waktu (ms) ketika jendela crop melompat ≥ `min_jump_px` (perpindahan wajah)."""
    return [t1 for (_, x0), (t1, x1) in zip(path.points, path.points[1:], strict=False)
            if abs(x1 - x0) >= min_jump_px]


def sendcmd_text(path: CropPath, duration_ms: int, fps: int = OUTPUT_FPS,
                 hard_cuts: bool = False) -> str:
    """Satu perintah `crop x` per frame keluaran. `hard_cuts`: tanpa interpolasi (podcast)."""
    lines = []
    frames = max(1, round(duration_ms * fps / 1000))
    j = 0
    for n in range(frames):
        t = n * 1000 / fps
        if hard_cuts:
            while j + 1 < len(path.points) and path.points[j + 1][0] <= t:
                j += 1
            x = path.points[j][1]
        else:
            x = path.x_at(t)
        lines.append(f"{t / 1000:.4f} crop x {round(x / 2) * 2};")
    return "\n".join(lines) + "\n"


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def filter_for_path(path: CropPath, cmd_file: Path, out_w: int = 1080, out_h: int = 1920) -> str:
    """Filtergraph `[0:v] → [vout]` untuk jalur crop (file perintah dari `sendcmd_text`)."""
    x0 = round(path.points[0][1] / 2) * 2
    return (f"[0:v]sendcmd=f='{_escape_filter_path(cmd_file)}',"
            f"crop={path.crop_w}:{path.crop_h}:{x0},"  # y default: tengah
            f"scale={out_w}:{out_h}:flags=lanczos,setsar=1[vout]")
