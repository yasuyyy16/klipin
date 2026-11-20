"""Model SQLAlchemy yang mencerminkan DDL 05-database.md §5.

Skema sebenarnya dibuat oleh migrasi Alembic (termasuk semua CHECK). Model ini harus tetap
sama dengan hasil migrasi; tes `test_models_match_migrations` menjaganya.
Waktu disimpan TEXT ISO-8601 UTC, boolean INTEGER 0/1, JSON TEXT (BR-010, §1).
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import REAL, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

NOW_SQL = text("(strftime('%Y-%m-%dT%H:%M:%SZ','now'))")


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JsonText(TypeDecorator):
    """JSON yang disimpan sebagai TEXT (kolom diberi CHECK json_valid di DDL)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        return None if value is None else json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect) -> Any:
        return None if value is None else json.loads(value)


class Base(DeclarativeBase):
    pass


DESC_INDEXES = {"ix_streams_status", "ix_clips_stream", "ix_jobs_claim", "ix_jobs_stream"}


def include_in_autogenerate(obj, name, type_, reflected, compare_to) -> bool:
    """Filter autogenerate: reflection SQLite tidak membaca ON DELETE pada FK inline maupun
    urutan DESC pada index, sehingga keduanya selalu tampak berbeda. FK dan index DESC
    dijaga lewat DDL migrasi dan tes constraint, bukan lewat perbandingan ini."""
    if type_ == "foreign_key_constraint":
        return False
    return not (type_ == "index" and name in DESC_INDEXES)


def pk() -> Mapped[int]:
    # DDL memakai `INTEGER PRIMARY KEY` tanpa NOT NULL; reflection SQLite melaporkannya nullable.
    return mapped_column(Integer, primary_key=True, nullable=True)


def created() -> Mapped[str]:
    return mapped_column(Text, nullable=False, server_default=NOW_SQL)


def updated() -> Mapped[str]:
    return mapped_column(Text, nullable=False, server_default=NOW_SQL, onupdate=utcnow)


def fk(target: str, ondelete: str, nullable: bool = True) -> Mapped[Any]:
    return mapped_column(Integer, ForeignKey(target, ondelete=ondelete), nullable=nullable)


def flag(default: int = 0) -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text(str(default)))


class LayoutPreset(Base):
    __tablename__ = "layout_presets"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_builtin: Mapped[int] = flag()
    params: Mapped[Any] = mapped_column(JsonText, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("platform", "external_id"),
        Index("ix_channels_default_preset", "default_layout_preset_id"),
    )
    id: Mapped[int] = pk()
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_layout_preset_id: Mapped[int | None] = fk("layout_presets.id", "SET NULL")
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class SourceStream(Base):
    __tablename__ = "source_streams"
    __table_args__ = (
        Index("ix_streams_channel", "channel_id"),
        Index("ix_streams_status", "status", text("created_at DESC")),
        Index("ix_streams_suggested_preset", "suggested_layout_preset_id"),
    )
    id: Mapped[int] = pk()
    channel_id: Mapped[int | None] = fk("channels.id", "SET NULL")
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    external_video_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    detected_language: Mapped[str | None] = mapped_column(Text)
    has_chat: Mapped[int] = flag()
    suggested_layout_preset_id: Mapped[int | None] = fk("layout_presets.id", "SET NULL")
    video_path: Mapped[str | None] = mapped_column(Text)
    video_width: Mapped[int | None] = mapped_column(Integer)
    video_height: Mapped[int | None] = mapped_column(Integer)
    video_fps: Mapped[float | None] = mapped_column(REAL)
    source_deleted_at: Mapped[str | None] = mapped_column(Text)
    live_analysis_enabled: Mapped[int] = flag()
    live_started_at: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class SubtitleStyle(Base):
    __tablename__ = "subtitle_styles"
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_builtin: Mapped[int] = flag()
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    font_family: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Montserrat'"))
    font_size: Mapped[int] = flag(64)
    primary_color: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'#FFFFFF'"))
    highlight_color: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'#FFD400'"))
    outline_color: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'#000000'"))
    outline_width: Mapped[int] = flag(4)
    uppercase: Mapped[int] = flag()
    max_words_per_line: Mapped[int] = flag(3)
    max_chars_per_line: Mapped[int] = flag(42)
    position_pct: Mapped[int] = flag(70)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class LiveMarker(Base):
    __tablename__ = "live_markers"
    __table_args__ = (Index("ix_markers_stream", "source_stream_id", "start_ms"),)
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = created()


class Clip(Base):
    __tablename__ = "clips"
    __table_args__ = (
        Index("ix_clips_stream", "source_stream_id", "status", text("score DESC")),
        Index("ix_clips_preset", "layout_preset_id"),
        Index("ix_clips_style", "subtitle_style_id"),
    )
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    live_marker_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("live_markers.id", ondelete="SET NULL"), unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'candidate'"))
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    score_audio: Mapped[float | None] = mapped_column(REAL)
    score_chat: Mapped[float | None] = mapped_column(REAL)
    score_llm: Mapped[int | None] = mapped_column(Integer)
    score_partial: Mapped[int] = flag()
    category: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    layout_preset_id: Mapped[int] = fk("layout_presets.id", "RESTRICT", nullable=False)
    subtitle_style_id: Mapped[int] = fk("subtitle_styles.id", "RESTRICT", nullable=False)
    subtitle_language: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'source'"))
    subtitle_overrides: Mapped[Any] = mapped_column(JsonText, nullable=True)
    translated_lines: Mapped[Any] = mapped_column(JsonText, nullable=True)
    caption_drafts: Mapped[Any] = mapped_column(JsonText, nullable=True)
    output_video_path: Mapped[str | None] = mapped_column(Text)
    output_srt_path: Mapped[str | None] = mapped_column(Text)
    rendered_at: Mapped[str | None] = mapped_column(Text)
    render_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class UploadAccount(Base):
    __tablename__ = "upload_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "external_account_id"),
        Index("ux_accounts_one_connected", "platform", unique=True,
              sqlite_where=text("account_status = 'connected'")),
    )
    id: Mapped[int] = pk()
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    keyring_ref: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    account_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'connected'"))
    token_expires_at: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[str] = created()
    last_error: Mapped[str | None] = mapped_column(Text)


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        Index("ix_uploads_clip", "clip_id"),
        Index("ix_uploads_account", "upload_account_id"),
        Index("ix_uploads_status_mode", "status", "mode"),
        Index("ux_uploads_active", "clip_id", "platform", unique=True,
              sqlite_where=text("status IN ('pending','uploading','uploaded')")),
    )
    id: Mapped[int] = pk()
    clip_id: Mapped[int] = fk("clips.id", "CASCADE", nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    upload_account_id: Mapped[int | None] = fk("upload_accounts.id", "RESTRICT")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    title: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    hashtags: Mapped[Any] = mapped_column(JsonText, nullable=False, server_default=text("'[]'"))
    visibility: Mapped[str | None] = mapped_column(Text)
    resumable_session_url: Mapped[str | None] = mapped_column(Text)
    platform_publish_id: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = flag()
    external_post_id: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)
    posted_as_private: Mapped[int] = flag()
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "awaiting_confirmation", "is_heavy",
              text("priority DESC"), "created_at"),
        Index("ix_jobs_stream", "source_stream_id", text("created_at DESC")),
        Index("ix_jobs_clip", "clip_id"),
        Index("ix_jobs_upload", "upload_id"),
        Index("ix_jobs_retry", "retry_of_job_id"),
    )
    id: Mapped[int] = pk()
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    source_stream_id: Mapped[int | None] = fk("source_streams.id", "CASCADE")
    clip_id: Mapped[int | None] = fk("clips.id", "CASCADE")
    upload_id: Mapped[int | None] = fk("uploads.id", "CASCADE")
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'final'"))
    preview_at_ms: Mapped[int | None] = mapped_column(Integer)
    scope_start_ms: Mapped[int | None] = mapped_column(Integer)
    scope_end_ms: Mapped[int | None] = mapped_column(Integer)
    is_heavy: Mapped[int] = flag(1)
    priority: Mapped[int] = flag()
    awaiting_confirmation: Mapped[int] = flag()
    progress_pct: Mapped[int] = flag()
    stage: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[Any] = mapped_column(JsonText, nullable=True)
    log_tail: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_of_job_id: Mapped[int | None] = fk("jobs.id", "SET NULL")
    worker_heartbeat_at: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class TranscriptionChunk(Base):
    __tablename__ = "transcription_chunks"
    __table_args__ = (UniqueConstraint("source_stream_id", "start_ms"),)
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    provider: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = flag()
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        Index("ix_segments_stream", "source_stream_id", "start_ms"),
        Index("ix_segments_chunk", "chunk_id"),
    )
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    chunk_id: Mapped[int] = fk("transcription_chunks.id", "CASCADE", nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = created()


class TranscriptWord(Base):
    __tablename__ = "transcript_words"
    __table_args__ = (
        Index("ix_words_stream", "source_stream_id", "start_ms"),
        Index("ix_words_segment", "segment_id"),
    )
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    segment_id: Mapped[int] = fk("transcript_segments.id", "CASCADE", nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_stream", "source_stream_id", "offset_ms"),)
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    offset_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_reaction: Mapped[int] = flag()
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'text'"))


class HighlightWindow(Base):
    __tablename__ = "highlight_windows"
    __table_args__ = (
        UniqueConstraint("source_stream_id", "start_ms"),
        Index("ix_windows_preselected", "source_stream_id", "preselected"),
    )
    id: Mapped[int] = pk()
    source_stream_id: Mapped[int] = fk("source_streams.id", "CASCADE", nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_signal: Mapped[float] = mapped_column(REAL, nullable=False)
    chat_signal: Mapped[float | None] = mapped_column(REAL)
    preselected: Mapped[int] = flag()
    llm_score: Mapped[int | None] = mapped_column(Integer)
    llm_category: Mapped[str | None] = mapped_column(Text)
    llm_reason: Mapped[str | None] = mapped_column(Text)
    llm_suggested_start_ms: Mapped[int | None] = mapped_column(Integer)
    llm_suggested_end_ms: Mapped[int | None] = mapped_column(Integer)
    llm_suggested_title: Mapped[str | None] = mapped_column(Text)
    llm_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_requested'"))
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class CamRegion(Base):
    __tablename__ = "cam_regions"
    __table_args__ = (
        Index("ix_regions_channel", "channel_id"),
        Index("ix_regions_stream", "source_stream_id"),
        Index("ix_regions_clip", "clip_id"),
        Index("ux_regions_channel_role", "channel_id", "role", unique=True,
              sqlite_where=text("channel_id IS NOT NULL")),
        Index("ux_regions_stream_role", "source_stream_id", "role", unique=True,
              sqlite_where=text("source_stream_id IS NOT NULL")),
        Index("ux_regions_clip_role", "clip_id", "role", unique=True,
              sqlite_where=text("clip_id IS NOT NULL")),
    )
    id: Mapped[int] = pk()
    channel_id: Mapped[int | None] = fk("channels.id", "CASCADE")
    source_stream_id: Mapped[int | None] = fk("source_streams.id", "CASCADE")
    clip_id: Mapped[int | None] = fk("clips.id", "CASCADE")
    role: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(REAL, nullable=False)
    y: Mapped[float] = mapped_column(REAL, nullable=False)
    w: Mapped[float] = mapped_column(REAL, nullable=False)
    h: Mapped[float] = mapped_column(REAL, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL)
    created_at: Mapped[str] = created()
    updated_at: Mapped[str] = updated()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True, nullable=True)
    value: Mapped[Any] = mapped_column(JsonText, nullable=False)
    updated_at: Mapped[str] = updated()
