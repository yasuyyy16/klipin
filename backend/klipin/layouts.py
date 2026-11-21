"""Preset Layout, Kanal, dan Region Cam (FR-006, FR-007, FR-008).

Region efektif sebuah Klip mengikuti prioritas 06-api.md: `clip` (override) → `channel`
(default Kanal) → `stream` (hasil `detect_layout`).
"""

from typing import Any

from sqlalchemy import Connection, func, select, text
from sqlalchemy.orm import Session

from klipin.api.errors import ApiError
from klipin.db.models import CamRegion, Channel, Clip, Job, LayoutPreset, SourceStream, utcnow
from klipin.layout.regions import MSG_NO_FACE

# Role Region Cam yang dipakai tiap preset (05-database.md `cam_regions.role`, FR-007).
ROLES_BY_PRESET: dict[str, set[str]] = {
    "gaming": {"cam", "content"},
    "custom": {"cam", "content"},
    "split_two": {"face_a", "face_b"},
    "podcast": {"face_a", "face_b"},
    "irl": set(),
    "center_crop": set(),
}
EDITABLE_CLIP = {"candidate", "approved", "rejected", "rendered", "render_failed"}
FOLLOWERS = ("candidate", "approved")  # Klip yang ikut default baru (apply_to_stream_clips)
MSG_PICK_CHANNEL = "Pilih Kanal dulu."
MSG_ROLES = {
    "none": "Preset ini tidak memakai Region Cam.",
    "gaming": "Preset Gaming butuh region cam dan content.",
    "split_two": "Preset Dua Orang butuh region face_a dan face_b.",
    "podcast": "Preset Podcast butuh region face_a dan face_b.",
    "custom": "Preset Kustom butuh 1–2 region (cam/content).",
}


def region_dict(r: Any) -> dict[str, Any]:
    out = {"role": r.role, "x": r.x, "y": r.y, "w": r.w, "h": r.h}
    if getattr(r, "confidence", None) is not None:
        out["confidence"] = r.confidence
    return out


def _regions(session: Session, **owner: int) -> list[CamRegion]:
    (column, value), = owner.items()
    return list(session.scalars(select(CamRegion).where(getattr(CamRegion, column) == value)
                                .order_by(CamRegion.role)))


def preset_dict(p: LayoutPreset | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"id": p.id, "code": p.code, "name": p.name, "is_builtin": bool(p.is_builtin),
            "params": p.params or {}}


def list_presets(session: Session) -> list[dict[str, Any]]:
    return [preset_dict(p) for p in session.scalars(select(LayoutPreset).order_by(LayoutPreset.id))]


# --- Kanal --------------------------------------------------------------------------------

def _get(session: Session, model: type, obj_id: int, message: str) -> Any:
    obj = session.get(model, obj_id)
    if obj is None:
        raise ApiError(404, "NOT_FOUND", message)
    return obj


def channel_dict(session: Session, c: Channel) -> dict[str, Any]:
    regions = _regions(session, channel_id=c.id)
    streams = session.scalar(select(func.count()).where(SourceStream.channel_id == c.id))
    return {"id": c.id, "platform": c.platform, "external_id": c.external_id, "name": c.name,
            "default_layout_preset": preset_dict(session.get(LayoutPreset,
                                                             c.default_layout_preset_id)
                                                 if c.default_layout_preset_id else None),
            "default_regions": [region_dict(r) for r in regions], "stream_count": streams}


def list_channels(session: Session) -> list[dict[str, Any]]:
    channels = session.scalars(select(Channel).order_by(func.lower(Channel.name), Channel.id))
    return [channel_dict(session, c) for c in channels]


def create_channel(session: Session, name: str) -> dict[str, Any]:
    """Kanal manual (`platform = local`) untuk Stream Sumber dari file lokal."""
    exists = session.scalar(select(Channel.id).where(
        Channel.platform == "local", func.lower(Channel.name) == name.lower()))
    if exists is not None:
        raise ApiError(409, "INVALID_STATE", "Kanal dengan nama ini sudah ada.",
                       {"existing_channel_id": str(exists)})
    channel = Channel(platform="local", external_id=None, name=name)
    session.add(channel)
    session.commit()
    return channel_dict(session, channel)


def set_stream_channel(session: Session, stream_id: int, channel_id: int) -> SourceStream:
    stream = _get(session, SourceStream, stream_id, "Stream Sumber tidak ditemukan.")
    _get(session, Channel, channel_id, "Kanal tidak ditemukan.")
    stream.channel_id = channel_id
    stream.updated_at = utcnow()
    session.commit()
    return stream


# --- Region -------------------------------------------------------------------------------

def stream_regions(session: Session, stream_id: int) -> dict[str, Any]:
    stream = _get(session, SourceStream, stream_id, "Stream Sumber tidak ditemukan.")
    suggested = (session.get(LayoutPreset, stream.suggested_layout_preset_id)
                 if stream.suggested_layout_preset_id else None)
    regions = _regions(session, source_stream_id=stream_id)
    detected = session.scalar(select(Job.id).where(
        Job.source_stream_id == stream_id, Job.job_type == "detect_layout",
        Job.status == "succeeded")) is not None
    channel = session.get(Channel, stream.channel_id) if stream.channel_id else None
    no_face = detected and not regions and suggested is not None and suggested.code == "center_crop"
    return {
        "stream_id": stream_id,
        "detected": detected,
        "suggested_layout_preset": preset_dict(suggested),
        "regions": [region_dict(r) for r in regions],
        "channel": channel_dict(session, channel) if channel else None,
        "message": MSG_NO_FACE if no_face else None,
    }


def effective_regions(conn: Connection, clip_id: int) -> tuple[str | None, list[dict[str, Any]]]:
    """(sumber, region) untuk render & tampilan: override Klip → default Kanal → deteksi."""
    owner = conn.execute(text(
        "SELECT c.source_stream_id, s.channel_id FROM clips c JOIN source_streams s "
        "ON s.id = c.source_stream_id WHERE c.id = :id"), {"id": clip_id}).first()
    if owner is None:
        return None, []
    stream_id, channel_id = owner
    for source, column, value in (("clip", "clip_id", clip_id),
                                  ("channel", "channel_id", channel_id),
                                  ("stream", "source_stream_id", stream_id)):
        if value is None:
            continue
        rows = conn.execute(text(
            f"SELECT role, x, y, w, h FROM cam_regions WHERE {column} = :v ORDER BY role"),
            {"v": value}).mappings().all()
        if rows:
            return source, [dict(r) for r in rows]
    return None, []


def _check_roles(code: str, roles: list[str], existing: set[str]) -> None:
    """Role harus milik preset; override gabungan (lama + baru, replace per role) harus lengkap."""
    allowed = ROLES_BY_PRESET[code]
    merged = existing | set(roles)
    if not allowed:
        msg = MSG_ROLES["none"]
    elif (not roles or not set(roles) <= allowed
          or (code != "custom" and merged != allowed)):
        msg = MSG_ROLES[code]
    else:
        msg = None
    if msg:
        raise ApiError(400, "VALIDATION_ERROR", msg, {"regions": msg})


def _upsert(session: Session, owner: dict[str, int], regions: list[dict[str, Any]]) -> None:
    (column, value), = owner.items()
    for r in regions:
        session.execute(text(f"DELETE FROM cam_regions WHERE {column} = :v AND role = :role"),
                        {"v": value, "role": r["role"]})
        session.add(CamRegion(**owner, role=r["role"], x=r["x"], y=r["y"], w=r["w"], h=r["h"],
                              confidence=None))
    session.flush()


def set_clip_regions(session: Session, clip_id: int, regions: list[dict[str, Any]],
                     save_as_channel_default: bool, apply_to_stream_clips: bool) -> dict[str, Any]:
    clip = _get(session, Clip, clip_id, "Klip tidak ditemukan.")
    if clip.status not in EDITABLE_CLIP:
        raise ApiError(409, "INVALID_STATE", "Klip sedang dirender. Tunggu sampai selesai.")
    preset = session.get(LayoutPreset, clip.layout_preset_id)
    existing = {r.role for r in _regions(session, clip_id=clip.id)}
    _check_roles(preset.code, [r["role"] for r in regions], existing)
    stream = session.get(SourceStream, clip.source_stream_id)
    if save_as_channel_default and stream.channel_id is None:
        raise ApiError(409, "INVALID_STATE", MSG_PICK_CHANNEL)

    _upsert(session, {"clip_id": clip.id}, regions)
    if clip.status in ("rendered", "render_failed"):  # 03-user-flow §4.3: edit → approved
        clip.status = "approved"
    clip.updated_at = utcnow()

    if save_as_channel_default:
        _upsert(session, {"channel_id": stream.channel_id}, regions)
        channel = session.get(Channel, stream.channel_id)
        channel.default_layout_preset_id = clip.layout_preset_id
        channel.updated_at = utcnow()

    affected: list[int] = []
    if apply_to_stream_clips:
        affected = list(session.scalars(select(Clip.id).where(
            Clip.source_stream_id == clip.source_stream_id, Clip.id != clip.id,
            Clip.status.in_(FOLLOWERS)).order_by(Clip.id)))
        if affected:
            session.execute(text(
                "DELETE FROM cam_regions WHERE clip_id IN (" + ",".join(map(str, affected)) + ")"))
            session.execute(text(
                "UPDATE clips SET updated_at = :now WHERE id IN ("
                + ",".join(map(str, affected)) + ")"), {"now": utcnow()})
    session.commit()
    return {"clip_id": clip.id, "regions_source": "clip", "affected_clip_ids": affected}
