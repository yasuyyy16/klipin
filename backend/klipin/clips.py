"""Klip: daftar, detail, transisi review, edit, Klip manual, jepret, data timeline (FR-014, FR-015).

Transisi status mengikuti 03-user-flow.md §4.3; transisi ke status yang sudah berlaku = 200
tanpa perubahan (06-api.md). Edit Klip `rendered`/`render_failed` → `approved` (perlu render
ulang); Klip `rendering` terkunci.
"""

from typing import Any

from sqlalchemy import Connection, func, select, text
from sqlalchemy.orm import Session

from klipin import app_settings, layouts
from klipin.api.errors import ApiError
from klipin.db.models import Clip, LayoutPreset, SourceStream, SubtitleStyle, utcnow

MIN_MS, MAX_MS = 15_000, 90_000  # BR-004
CLIP_STATUSES = {"candidate", "approved", "rejected", "rendering", "rendered", "render_failed"}
MSG_DURATION = "Durasi klip harus 15–90 detik."
MSG_LOCKED = "Klip sedang dirender. Tunggu sampai selesai."
MSG_SOURCE_DELETED = "Video sumber sudah dihapus."
# aksi → (status asal yang sah, status tujuan)
TRANSITIONS = {
    "approve": ({"candidate"}, "approved"),
    "reject": ({"candidate", "approved"}, "rejected"),
    "restore": ({"rejected"}, "candidate"),
    "unapprove": ({"approved"}, "candidate"),
}
ACTION_LABEL = {"approve": "disetujui", "reject": "ditolak", "restore": "dipulihkan",
                "unapprove": "dibatalkan persetujuannya"}
TRANSCRIPT_MAX_MS = 30 * 60_000
SNAP_MS = 2_000


def get_clip(session: Session, clip_id: int) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise ApiError(404, "NOT_FOUND", "Klip tidak ditemukan.")
    return clip


def get_stream(session: Session, stream_id: int) -> SourceStream:
    stream = session.get(SourceStream, stream_id)
    if stream is None:
        raise ApiError(404, "NOT_FOUND", "Stream Sumber tidak ditemukan.")
    return stream


def _uploads(session: Session, clip_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {i: [] for i in clip_ids}
    if clip_ids:
        for cid, platform, mode, status in session.execute(text(
                "SELECT clip_id, platform, mode, status FROM uploads WHERE clip_id IN ("
                + ",".join(map(str, clip_ids)) + ") ORDER BY id")):
            out[cid].append({"platform": platform, "mode": mode, "status": status})
    return out


def summary(c: Clip, uploads: list[dict]) -> dict[str, Any]:
    return {"id": c.id, "source_stream_id": c.source_stream_id, "origin": c.origin,
            "status": c.status, "start_ms": c.start_ms, "end_ms": c.end_ms,
            "duration_ms": c.end_ms - c.start_ms, "score": c.score,
            "score_partial": bool(c.score_partial), "category": c.category, "reason": c.reason,
            "title": c.title, "layout_preset_id": c.layout_preset_id,
            "needs_rerender": needs_rerender(c), "uploads": uploads}


def needs_rerender(c: Clip) -> bool:
    return c.output_video_path is not None and c.status != "rendered"


def list_clips(session: Session, stream_id: int, statuses: list[str] | None, sort: str,
               limit: int, offset: int) -> tuple[list[dict], int]:
    get_stream(session, stream_id)
    query = select(Clip).where(Clip.source_stream_id == stream_id)
    query = (query.where(Clip.status.in_(statuses)) if statuses
             else query.where(Clip.status != "rejected"))  # default: semua kecuali ditolak
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    order = ((Clip.start_ms, Clip.id) if sort == "start"
             else (Clip.score.desc().nulls_last(), Clip.start_ms, Clip.id))
    items = list(session.scalars(query.order_by(*order).limit(limit).offset(offset)))
    uploads = _uploads(session, [c.id for c in items])
    return [summary(c, uploads[c.id]) for c in items], total


def detail(session: Session, c: Clip) -> dict[str, Any]:
    stream = session.get(SourceStream, c.source_stream_id)
    preset = session.get(LayoutPreset, c.layout_preset_id)
    source, regions = layouts.effective_regions(session.connection(), c.id)
    language = stream.detected_language
    languages = ["source"] + (["id"] if language and language != "id" else [])
    output = None
    if c.output_video_path:
        output = {"video_url": f"/api/v1/media/clips/{c.id}/video",
                  "srt_url": f"/api/v1/media/clips/{c.id}/srt", "rendered_at": c.rendered_at}
    return {
        **summary(c, _uploads(session, [c.id])[c.id]),
        "score_breakdown": {"audio": c.score_audio, "chat": c.score_chat, "llm": c.score_llm,
                            "partial": bool(c.score_partial)},
        "layout_preset": {"id": preset.id, "code": preset.code, "params": preset.params or {}},
        "regions": {"source": source, "items": regions},
        "subtitle_style_id": c.subtitle_style_id, "subtitle_language": c.subtitle_language,
        "available_languages": languages, "detected_language": language,
        "subtitle_overrides": c.subtitle_overrides, "translated_lines": c.translated_lines,
        "render_error": c.render_error, "output": output,
    }


def _duration_error() -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", MSG_DURATION, {"duration_ms": MSG_DURATION})


def transition(session: Session, clip_id: int, action: str) -> Clip:
    clip = get_clip(session, clip_id)
    sources, target = TRANSITIONS[action]
    if clip.status == target:
        return clip  # idempoten
    if clip.status not in sources:
        raise ApiError(409, "INVALID_STATE",
                       f"Klip berstatus {clip.status} tidak bisa {ACTION_LABEL[action]}.")
    if target == "approved" and not MIN_MS <= clip.end_ms - clip.start_ms <= MAX_MS:
        raise _duration_error()
    clip.status = target
    clip.updated_at = utcnow()
    session.commit()
    return clip


def _check_range(stream: SourceStream, start_ms: int, end_ms: int) -> None:
    if start_ms >= end_ms:
        msg = "Waktu selesai harus setelah waktu mulai."
        raise ApiError(400, "VALIDATION_ERROR", msg, {"end_ms": msg})
    if stream.duration_ms is not None and end_ms > stream.duration_ms:
        msg = "Rentang di luar durasi video."
        raise ApiError(400, "VALIDATION_ERROR", msg, {"end_ms": msg})


def patch(session: Session, clip_id: int, changes: dict[str, Any]) -> tuple[Clip, list[str]]:
    """Edit Klip (FR-015). Mengembalikan (klip, peringatan)."""
    clip = get_clip(session, clip_id)
    if clip.status == "rendering":
        raise ApiError(409, "INVALID_STATE", MSG_LOCKED)
    stream = session.get(SourceStream, clip.source_stream_id)
    warnings: list[str] = []
    if "start_ms" in changes or "end_ms" in changes:
        start = changes.get("start_ms", clip.start_ms)
        end = changes.get("end_ms", clip.end_ms)
        if stream.source_deleted_at:
            raise ApiError(409, "SOURCE_DELETED", MSG_SOURCE_DELETED)
        _check_range(stream, start, end)
        if clip.status in ("approved", "rendered", "render_failed") and not (
                MIN_MS <= end - start <= MAX_MS):
            raise _duration_error()
        clip.start_ms, clip.end_ms = start, end
    if "layout_preset_id" in changes:
        if session.get(LayoutPreset, changes["layout_preset_id"]) is None:
            raise ApiError(400, "VALIDATION_ERROR", "Preset Layout tidak ditemukan.",
                           {"layout_preset_id": "Preset Layout tidak ditemukan."})
        clip.layout_preset_id = changes["layout_preset_id"]
    if "subtitle_style_id" in changes:
        if session.get(SubtitleStyle, changes["subtitle_style_id"]) is None:
            raise ApiError(400, "VALIDATION_ERROR", "Gaya Subtitle tidak ditemukan.",
                           {"subtitle_style_id": "Gaya Subtitle tidak ditemukan."})
        clip.subtitle_style_id = changes["subtitle_style_id"]
    if "subtitle_language" in changes:
        lang = changes["subtitle_language"]
        if lang == "id" and (stream.detected_language or "id") == "id":
            msg = "Stream ini sudah berbahasa Indonesia; terjemahan tidak diperlukan."
            raise ApiError(400, "VALIDATION_ERROR", msg, {"subtitle_language": msg})
        clip.subtitle_language = lang
    for key in ("title", "subtitle_overrides", "translated_lines"):
        if key in changes:
            setattr(clip, key, changes[key])
    if clip.subtitle_language == "id":
        style = session.get(SubtitleStyle, clip.subtitle_style_id)
        if style is not None and style.mode == "word_highlight":  # BR-008
            warnings.append("Terjemahan memakai mode kalimat")
    if clip.status in ("rendered", "render_failed"):  # 03-user-flow §4.3: edit → approved
        clip.status = "approved"
        if not MIN_MS <= clip.end_ms - clip.start_ms <= MAX_MS:
            raise _duration_error()
    clip.updated_at = utcnow()
    session.commit()
    return clip, warnings


def defaults(conn: Connection, stream_id: int) -> tuple[int, int, str]:
    """(preset: default Kanal → saran → center_crop, gaya subtitle default, nama Kanal/judul)."""
    row = conn.execute(text(
        "SELECT c.default_layout_preset_id, s.suggested_layout_preset_id, c.name, s.title "
        "FROM source_streams s LEFT JOIN channels c ON c.id = s.channel_id WHERE s.id = :s"),
        {"s": stream_id}).one()
    preset = row[0] or row[1] or conn.execute(text(
        "SELECT id FROM layout_presets WHERE code = 'center_crop' ORDER BY id LIMIT 1")).scalar()
    style = conn.execute(text("SELECT id FROM subtitle_styles WHERE name = :n"),
                         {"n": app_settings.value(conn, "default_subtitle_style")}).scalar() \
        or conn.execute(text("SELECT id FROM subtitle_styles ORDER BY is_builtin DESC, id "
                             "LIMIT 1")).scalar()
    return preset, style, (row[2] or row[3])


def clock(ms: int) -> str:
    s = ms // 1000
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def create_manual(session: Session, stream_id: int, start_ms: int, end_ms: int) -> Clip:
    stream = get_stream(session, stream_id)
    if stream.source_deleted_at:
        raise ApiError(409, "SOURCE_DELETED", MSG_SOURCE_DELETED)
    _check_range(stream, start_ms, end_ms)
    preset, style, name = defaults(session.connection(), stream_id)
    clip = Clip(source_stream_id=stream_id, origin="manual", status="candidate",
                start_ms=start_ms, end_ms=end_ms, layout_preset_id=preset,
                subtitle_style_id=style, title=f"{name} - {clock(start_ms)}"[:100])
    session.add(clip)
    session.commit()
    return clip


def snap(session: Session, clip_id: int, edge: str, position_ms: int) -> dict[str, Any]:
    """Batas Segmen Transkrip terdekat (awal segmen untuk `start`, akhir untuk `end`) ±2 dtk."""
    clip = get_clip(session, clip_id)
    column = "start_ms" if edge == "start" else "end_ms"
    row = session.execute(text(
        f"SELECT id, {column} FROM transcript_segments WHERE source_stream_id = :s "
        f"AND {column} BETWEEN :lo AND :hi ORDER BY abs({column} - :p), id LIMIT 1"),
        {"s": clip.source_stream_id, "lo": position_ms - SNAP_MS, "hi": position_ms + SNAP_MS,
         "p": position_ms}).first()
    if row is None:
        return {"snapped_ms": position_ms, "segment_id": None}
    return {"snapped_ms": row[1], "segment_id": row[0]}


def transcript(session: Session, stream_id: int, from_ms: int, to_ms: int) -> dict[str, Any]:
    get_stream(session, stream_id)
    if to_ms <= from_ms or to_ms - from_ms > TRANSCRIPT_MAX_MS:
        msg = "Rentang transkrip maksimal 30 menit."
        raise ApiError(400, "VALIDATION_ERROR", msg, {"to_ms": msg})
    segments = session.execute(text(
        "SELECT id, start_ms, end_ms, speaker, text FROM transcript_segments "
        "WHERE source_stream_id = :s AND end_ms >= :a AND start_ms <= :b ORDER BY start_ms, id"),
        {"s": stream_id, "a": from_ms, "b": to_ms}).all()
    words: dict[int, list[dict]] = {s.id: [] for s in segments}
    if segments:
        for wid, seg, a, b, word, conf in session.execute(text(
                "SELECT id, segment_id, start_ms, end_ms, word, confidence FROM transcript_words "
                "WHERE segment_id IN (" + ",".join(str(s.id) for s in segments) + ") "
                "ORDER BY start_ms, id")):
            words[seg].append({"id": wid, "start_ms": a, "end_ms": b, "word": word,
                               "confidence": conf})
    return {"segments": [{"id": s.id, "start_ms": s.start_ms, "end_ms": s.end_ms,
                          "speaker": s.speaker, "text": s.text, "words": words[s.id]}
                         for s in segments]}


def timeline(session: Session, stream_id: int, bucket_ms: int) -> dict[str, Any]:
    """Heatmap: tiap ember = Sinyal tertinggi jendela yang beririsan (LLM 0–1, null bila belum)."""
    stream = get_stream(session, stream_id)
    duration = stream.duration_ms or 0
    rows = session.execute(text(
        "SELECT start_ms, end_ms, audio_signal, chat_signal, llm_status, llm_score "
        "FROM highlight_windows WHERE source_stream_id = :s"), {"s": stream_id}).all()
    buckets = []
    for b0 in range(0, max(duration, 1), bucket_ms):
        b1 = b0 + bucket_ms
        hits = [r for r in rows if r.start_ms < b1 and r.end_ms > b0]
        chat = [r.chat_signal for r in hits if r.chat_signal is not None]
        llm = [r.llm_score / 100 for r in hits if r.llm_status == "done" and r.llm_score is not None]
        buckets.append({"start_ms": b0,
                        "audio": round(max((r.audio_signal for r in hits), default=0.0), 4),
                        "chat": round(max(chat), 4) if chat else None,
                        "llm": round(max(llm), 4) if llm else None})
    clip_rows = session.execute(select(Clip.id, Clip.start_ms, Clip.end_ms, Clip.status)
                                .where(Clip.source_stream_id == stream_id)
                                .order_by(Clip.start_ms)).all()
    return {"buckets": buckets,
            "clips": [{"id": i, "start_ms": a, "end_ms": b, "status": st}
                      for i, a, b, st in clip_rows]}
