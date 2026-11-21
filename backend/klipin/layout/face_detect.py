"""Deteksi wajah lokal di CPU (FR-006, INT-09): MediaPipe BlazeFace, cadangan OpenCV DNN (YuNet).

Model dibundel di `layout/models/` (lihat README di sana). Per frame: MediaPipe dulu; bila
tidak menemukan wajah (mis. wajah kecil di facecam pada frame besar) atau MediaPipe tidak
tersedia, YuNet dijalankan pada resolusi frame penuh. Koordinat keluaran ternormalisasi 0–1.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
import structlog

log = structlog.get_logger(__name__)

MODELS = Path(__file__).resolve().parent / "models"
BLAZEFACE = MODELS / "blaze_face_short_range.tflite"
YUNET = MODELS / "face_detection_yunet_2023mar.onnx"
MIN_SCORE = 0.6


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


def _clip_face(x: float, y: float, w: float, h: float, fw: int, fh: int, score: float) -> Face | None:
    x0, y0 = max(0.0, x / fw), max(0.0, y / fh)
    x1, y1 = min(1.0, (x + w) / fw), min(1.0, (y + h) / fh)
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    return Face(x0, y0, x1 - x0, y1 - y0, float(score))


class Detector(Protocol):
    def detect(self, frame_bgr: np.ndarray) -> list[Face]: ...


class MediaPipeDetector:
    def __init__(self) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._det = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(BLAZEFACE)),
            min_detection_confidence=MIN_SCORE))

    def detect(self, frame_bgr: np.ndarray) -> list[Face]:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._det.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb))
        faces = []
        for d in result.detections:
            b = d.bounding_box
            face = _clip_face(b.origin_x, b.origin_y, b.width, b.height, w, h,
                              d.categories[0].score if d.categories else 0.0)
            if face:
                faces.append(face)
        return faces


class YuNetDetector:
    def __init__(self) -> None:
        self._det = cv2.FaceDetectorYN.create(str(YUNET), "", (320, 320), MIN_SCORE)

    def detect(self, frame_bgr: np.ndarray) -> list[Face]:
        h, w = frame_bgr.shape[:2]
        self._det.setInputSize((w, h))
        _, found = self._det.detect(frame_bgr)
        faces = []
        for f in [] if found is None else found:
            face = _clip_face(float(f[0]), float(f[1]), float(f[2]), float(f[3]), w, h,
                              float(f[14]))
            if face:
                faces.append(face)
        return faces


class FaceDetector:
    """MediaPipe → YuNet per frame. Gagal memuat MediaPipe → hanya YuNet."""

    def __init__(self) -> None:
        self.primary: Any = None
        try:
            self.primary = MediaPipeDetector()
        except Exception as e:  # noqa: BLE001 — paket/model MediaPipe rusak: pakai cadangan
            log.warning("MediaPipe tidak tersedia, memakai YuNet", error=str(e))
        self.fallback = YuNetDetector()

    @property
    def name(self) -> str:
        return "mediapipe+yunet" if self.primary else "yunet"

    def detect(self, frame_bgr: np.ndarray) -> list[Face]:
        faces = self.primary.detect(frame_bgr) if self.primary else []
        return faces or self.fallback.detect(frame_bgr)
