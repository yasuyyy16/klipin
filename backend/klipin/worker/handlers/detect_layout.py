"""Job `detect_layout` (FR-006, ADR-004): sampel frame → wajah → saran Preset Layout + Region Cam.

- Sampel merata 1 frame per 10 detik (maks. 600; minimal 10 untuk video pendek), dibaca dengan
  seek OpenCV dan diperkecil ke lebar 960 px.
- Wajah per sampel disimpan di checkpoint (`faces`) sehingga coba ulang tidak mendeteksi ulang.
- Hasil: `cam_regions` milik Stream Sumber (diganti seluruhnya) dan
  `source_streams.suggested_layout_preset_id`.
- Kanal dengan Preset Layout default: preset Kanal dipakai sebagai saran; deteksi hanya
  memverifikasi (dicatat di log Job).
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import Connection, text

from klipin.db.models import utcnow
from klipin.layout.face_detect import Face, FaceDetector
from klipin.layout.regions import Region, Suggestion, iou, suggest
from klipin.media import probe
from klipin.worker.context import JobContext
from klipin.worker.handlers import register

INTERVAL_MS = 10_000
MAX_FRAMES = 600
MIN_FRAMES = 10
EDGE_FRAMES = 30
FRAME_WIDTH = 960
CHECKPOINT_EVERY = 25
MSG_NO_SOURCE = "Video sumber tidak tersedia, deteksi layout tidak bisa dilakukan."
MSG_UNREADABLE = "Video sumber tidak bisa dibaca."


def sample_times(duration_ms: int) -> list[int]:
    n = max(MIN_FRAMES, min(MAX_FRAMES, duration_ms // INTERVAL_MS))
    step = duration_ms / n
    return [int(step * (i + 0.5)) for i in range(n)]


def _read(cap: cv2.VideoCapture, t_ms: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_MSEC, t_ms)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    h, w = frame.shape[:2]
    if w > FRAME_WIDTH:
        frame = cv2.resize(frame, (FRAME_WIDTH, round(h * FRAME_WIDTH / w)),
                           interpolation=cv2.INTER_AREA)
    return frame


def _gray_frames(cap: cv2.VideoCapture, times: list[int]) -> list[np.ndarray]:
    stride = max(1, len(times) // EDGE_FRAMES)
    frames = (_read(cap, t) for t in times[::stride][:EDGE_FRAMES])
    return [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames if f is not None]


def _preset_id(conn: Connection, code: str) -> int | None:
    return conn.execute(text("SELECT id FROM layout_presets WHERE code = :c "
                             "ORDER BY is_builtin DESC, id LIMIT 1"), {"c": code}).scalar()


def _verify_channel(ctx: JobContext, conn: Connection, channel_id: int,
                    found: Suggestion) -> int | None:
    """Preset default Kanal (bila ada) menang; catat apakah deteksi cocok dengannya."""
    row = conn.execute(text(
        "SELECT p.id, p.code FROM channels c JOIN layout_presets p "
        "ON p.id = c.default_layout_preset_id WHERE c.id = :c"), {"c": channel_id}).first()
    if row is None:
        return None
    preset_id, code = row
    saved = conn.execute(text("SELECT role, x, y, w, h FROM cam_regions WHERE channel_id = :c"),
                         {"c": channel_id}).all()
    detected = {r.role: r for r in found.regions}
    notes = [f"Preset default Kanal dipakai: {code} (deteksi: {found.preset})."]
    for role, x, y, w, h in saved:
        if role in detected:
            score = iou(Region(role, x, y, w, h, None), detected[role])
            notes.append(f"Region {role} Kanal vs deteksi: IoU {score:.2f}"
                         + (" (cocok)" if score >= 0.8 else " (berbeda, cek di Editor)"))
    ctx.log(" ".join(notes))
    return preset_id


def _store(ctx: JobContext, found: Suggestion, channel_id: int | None) -> None:
    stream_id = ctx.source_stream_id
    with ctx.engine.begin() as conn:
        preset_id = _verify_channel(ctx, conn, channel_id, found) if channel_id else None
        if preset_id is None:
            preset_id = _preset_id(conn, found.preset)
        conn.execute(text("DELETE FROM cam_regions WHERE source_stream_id = :s"), {"s": stream_id})
        for r in found.regions:
            conn.execute(text(
                "INSERT INTO cam_regions (source_stream_id, role, x, y, w, h, confidence) "
                "VALUES (:s, :role, :x, :y, :w, :h, :c)"),
                {"s": stream_id, "role": r.role, "x": r.x, "y": r.y, "w": r.w, "h": r.h,
                 "c": r.confidence})
        conn.execute(text("UPDATE source_streams SET suggested_layout_preset_id = :p, "
                          "updated_at = :now WHERE id = :s"),
                     {"p": preset_id, "now": utcnow(), "s": stream_id})


def run(ctx: JobContext, *, detector_factory: Callable[[], object] = FaceDetector) -> Suggestion:
    with ctx.engine.connect() as conn:
        video, duration, channel_id, deleted = conn.execute(text(
            "SELECT video_path, duration_ms, channel_id, source_deleted_at FROM source_streams "
            "WHERE id = :s"), {"s": ctx.source_stream_id}).one()
    if not video or deleted or not Path(video).is_file():
        raise RuntimeError(MSG_NO_SOURCE)
    try:
        duration = duration or probe.duration_ms(Path(video))
    except ValueError as e:
        raise RuntimeError(MSG_UNREADABLE) from e
    times = sample_times(duration)

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(MSG_UNREADABLE)
    try:
        faces_by_t: dict[str, list[list[float]]] = dict(ctx.checkpoint.get("faces") or {})
        if faces_by_t:
            ctx.log(f"{len(faces_by_t)}/{len(times)} sampel sudah dideteksi, dilewati")
        detector = None
        unreadable = 0
        for i, t in enumerate(times):
            if str(t) in faces_by_t:
                continue
            ctx.progress(i * 90 // len(times), f"Deteksi wajah {i + 1}/{len(times)}")
            frame = _read(cap, t)
            if frame is None:
                unreadable += 1
                faces: list[Face] = []
            else:
                detector = detector or detector_factory()
                faces = detector.detect(frame)
            faces_by_t[str(t)] = [[f.x, f.y, f.w, f.h, f.score] for f in faces]
            if (i + 1) % CHECKPOINT_EVERY == 0:
                ctx.save_checkpoint({**ctx.checkpoint, "faces": faces_by_t})
        if unreadable == len(times):
            raise RuntimeError(MSG_UNREADABLE)
        ctx.save_checkpoint({**ctx.checkpoint, "faces": faces_by_t})

        ctx.progress(92, "Menyusun saran layout")
        samples = [[Face(*f) for f in faces_by_t[str(t)]] for t in times]
        found = suggest(samples, lambda: _gray_frames(cap, times))
    finally:
        cap.release()

    _store(ctx, found, channel_id)
    detail = ", ".join(f"{k}={v}" for k, v in found.stats.items())
    ctx.log(f"saran preset: {found.preset} ({detail})"
            + (f" — {found.message}" if found.message else ""))
    if detector is not None:
        ctx.log(f"detektor: {getattr(detector, 'name', type(detector).__name__)}")
    ctx.progress(100, "Selesai")
    return found


@register("detect_layout")
def handle(ctx: JobContext) -> None:
    run(ctx)
