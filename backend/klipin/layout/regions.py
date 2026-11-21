"""Saran Preset Layout + Region Cam dari wajah per sampel frame (FR-006, ADR-004).

Aturan (FR-006):
- Tanpa wajah di ≥ 90% sampel → `center_crop`, tanpa region.
- ≥ 2 wajah sekaligus di ≥ 50% sampel berwajah → `podcast`; `face_a` (kiri), `face_b` (kanan).
- Satu wajah dominan, posisinya stabil (sebaran pusat ≤ 8% frame) dan kecil (< 25% luas) →
  `gaming`; `cam` = kotak panel facecam (kotak wajah diperluas ke tepi panel yang konsisten
  antar-frame), `content` = sisi frame di luar kolom cam.
- Selain itu (wajah besar dan/atau bergerak) → `irl` (crop dinamis dihitung saat render).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median

import cv2
import numpy as np

from klipin.layout.face_detect import Face

NO_FACE_MAX_RATIO = 0.10  # wajah di < 10% sampel = "tidak ada wajah di ≥ 90% sampel"
MULTI_FACE_MIN_RATIO = 0.5
STABLE_SPREAD = 0.08
SMALL_FACE_AREA = 0.25
EDGE_MIN_RATIO = 2.0  # sisi terlemah panel minimal 2× rata-rata gradien frame
PEAKS_PER_SIDE = 6
SEARCH_FACTOR = 1.5  # cari tepi panel sampai 1,5× ukuran wajah dari tepi wajah
FALLBACK_PAD = 0.4  # bila tepi panel tidak jelas: wajah + 40% ukurannya di tiap sisi
FACE_PAD = 0.3  # region face_a/face_b: wajah + 30% di tiap sisi
MIN_REGION = 0.05  # CHECK cam_regions.w/h ≥ 0,05
MSG_NO_FACE = "Wajah tidak terdeteksi. Tandai area kamera manual jika ada."


@dataclass(frozen=True)
class Region:
    role: str
    x: float
    y: float
    w: float
    h: float
    confidence: float | None


@dataclass
class Suggestion:
    preset: str
    regions: list[Region] = field(default_factory=list)
    message: str | None = None
    stats: dict = field(default_factory=dict)


def _clamp_box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(1.0, x1), min(1.0, y1)
    if x1 - x0 < MIN_REGION:
        x1 = min(1.0, x0 + MIN_REGION)
        x0 = x1 - MIN_REGION
    if y1 - y0 < MIN_REGION:
        y1 = min(1.0, y0 + MIN_REGION)
        y0 = y1 - MIN_REGION
    return round(x0, 6), round(y0, 6), round(x1 - x0, 6), round(y1 - y0, 6)


def _padded(face_box: tuple[float, float, float, float], pad: float, role: str,
            confidence: float) -> Region:
    x0, y0, x1, y1 = face_box
    w, h = x1 - x0, y1 - y0
    return Region(role, *_clamp_box(x0 - pad * w, y0 - pad * h, x1 + pad * w, y1 + pad * h),
                  confidence)


def _median_box(faces: list[Face]) -> tuple[float, float, float, float]:
    return (median(f.x for f in faces), median(f.y for f in faces),
            median(f.x + f.w for f in faces), median(f.y + f.h for f in faces))


def _peaks(profile: np.ndarray, lo: float, hi: float, k: int = PEAKS_PER_SIDE) -> list[int]:
    """Indeks k puncak terkuat di [lo, hi] (jarak antar-puncak ≥ 4 px)."""
    lo_i, hi_i = max(0, int(lo)), min(len(profile) - 1, int(hi))
    if hi_i <= lo_i:
        return []
    picked: list[int] = []
    for i in np.argsort(profile[lo_i:hi_i + 1])[::-1]:
        idx = lo_i + int(i)
        if all(abs(idx - p) >= 4 for p in picked):
            picked.append(idx)
            if len(picked) == k:
                break
    return picked


def cam_panel(frames_gray: list[np.ndarray], face_box: tuple[float, float, float, float],
              confidence: float) -> Region:
    """Perluas kotak wajah ke tepi panel facecam: tepi overlay statis tetap kuat setelah
    gradien dirata-rata antar-frame, sedangkan tepi gameplay yang bergerak memudar."""
    if not frames_gray:
        return _padded(face_box, FALLBACK_PAD, "cam", confidence)
    stack = [g.astype(np.float32) for g in frames_gray]
    ev = np.mean([np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)) for g in stack], axis=0)
    eh = np.mean([np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)) for g in stack], axis=0)
    height, width = stack[0].shape
    fx0, fy0, fx1, fy1 = (face_box[0] * width, face_box[1] * height,
                          face_box[2] * width, face_box[3] * height)
    fw, fh = fx1 - fx0, fy1 - fy0
    pad_x, pad_y = FALLBACK_PAD * fw, FALLBACK_PAD * fh
    ev_ref, eh_ref = float(np.mean(ev)) + 1e-6, float(np.mean(eh)) + 1e-6

    # Kandidat tiap sisi: puncak gradien di dekat wajah + posisi cadangan (wajah + 40%) +
    # tepi frame. Garis gameplay statis bisa jadi puncak di satu sisi, tetapi jarang membentuk
    # persegi panjang yang keempat sisinya kuat — itu ciri panel facecam.
    rows = slice(int(max(0, fy0 - 0.5 * fh)), int(min(height, fy1 + 0.5 * fh)))
    cols = slice(int(max(0, fx0 - 0.5 * fw)), int(min(width, fx1 + 0.5 * fw)))
    col_profile, row_profile = ev[rows].mean(axis=0), eh[:, cols].mean(axis=1)
    lefts = _peaks(col_profile, fx0 - SEARCH_FACTOR * fw, fx0 - 2) + [max(0, int(fx0 - pad_x)), 0]
    rights = ([p + 1 for p in _peaks(col_profile, fx1 + 2, fx1 + SEARCH_FACTOR * fw)]
              + [min(width, int(fx1 + pad_x)), width])
    tops = _peaks(row_profile, fy0 - SEARCH_FACTOR * fh, fy0 - 2) + [max(0, int(fy0 - pad_y)), 0]
    bottoms = ([p + 1 for p in _peaks(row_profile, fy1 + 2, fy1 + SEARCH_FACTOR * fh)]
               + [min(height, int(fy1 + pad_y)), height])

    def side_v(x: int, t: int, b: int) -> float:
        if x <= 0 or x >= width:
            return EDGE_MIN_RATIO  # tepi frame: dianggap batas yang wajar
        return float(np.mean(ev[t:b, min(x, width - 1)])) / ev_ref

    def side_h(y: int, left: int, right: int) -> float:
        if y <= 0 or y >= height:
            return EDGE_MIN_RATIO
        return float(np.mean(eh[min(y, height - 1), left:right])) / eh_ref

    best, best_score = None, -1.0
    for left in set(lefts):
        for right in set(rights):
            if right - left < MIN_REGION * width:
                continue
            for top in set(tops):
                for bottom in set(bottoms):
                    if bottom - top < MIN_REGION * height:
                        continue
                    # Sisi terlemah yang menentukan: satu garis gameplay yang sangat kuat
                    # tidak boleh menutupi sisi lain yang lemah.
                    score = min(side_v(left, top, bottom), side_v(right - 1, top, bottom),
                                side_h(top, left, right), side_h(bottom - 1, left, right))
                    if score > best_score:
                        best, best_score = (left, top, right, bottom), score
    if best is None or best_score < EDGE_MIN_RATIO:
        return _padded(face_box, FALLBACK_PAD, "cam", confidence)
    left, top, right, bottom = best
    return Region("cam", *_clamp_box(left / width, top / height, right / width, bottom / height),
                  confidence)


def content_beside(cam: Region) -> Region:
    """Area konten = sisi frame di luar kolom cam bila lebarnya ≥ 50%, selain itu seluruh frame."""
    right_edge = cam.x + cam.w
    if cam.x >= 0.5:
        return Region("content", 0.0, 0.0, round(cam.x, 6), 1.0, None)
    if 1 - right_edge >= 0.5:
        return Region("content", round(right_edge, 6), 0.0, round(1 - right_edge, 6), 1.0, None)
    return Region("content", 0.0, 0.0, 1.0, 1.0, None)


def suggest(samples: list[list[Face]],
            load_frames: Callable[[], list[np.ndarray]] = list) -> Suggestion:
    """`load_frames` (frame abu-abu) hanya dipanggil bila perlu mencari tepi panel cam."""
    total = len(samples)
    with_face = [faces for faces in samples if faces]
    stats: dict = {"samples": total, "with_face": len(with_face)}
    if total == 0 or len(with_face) < NO_FACE_MAX_RATIO * total:
        return Suggestion("center_crop", message=MSG_NO_FACE, stats=stats)
    presence = len(with_face) / total

    multi = [sorted(faces, key=lambda f: f.area, reverse=True)[:2] for faces in with_face
             if len(faces) >= 2]
    stats["multi_face"] = len(multi)
    if len(multi) >= MULTI_FACE_MIN_RATIO * len(with_face):
        lefts = [min(pair, key=lambda f: f.cx) for pair in multi]
        rights = [max(pair, key=lambda f: f.cx) for pair in multi]
        conf = round(len(multi) / total, 3)
        return Suggestion("podcast", [_padded(_median_box(lefts), FACE_PAD, "face_a", conf),
                                      _padded(_median_box(rights), FACE_PAD, "face_b", conf)],
                          stats=stats)

    main = [max(faces, key=lambda f: f.area) for faces in with_face]
    spread = max(max(f.cx for f in main) - min(f.cx for f in main),
                 max(f.cy for f in main) - min(f.cy for f in main))
    area = median(f.area for f in main)
    stats.update(spread=round(spread, 4), face_area=round(area, 4))
    if spread <= STABLE_SPREAD and area < SMALL_FACE_AREA:
        cam = cam_panel(load_frames(), _median_box(main), round(presence, 3))
        return Suggestion("gaming", [cam, content_beside(cam)], stats=stats)
    return Suggestion("irl", stats=stats)


def iou(a: Region, b: Region) -> float:
    iw = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    ih = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = iw * ih
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0
