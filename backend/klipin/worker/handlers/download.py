"""Job `download`: unduh VOD ≤ 1080p + chat replay YouTube (FR-001, FR-010, INT-01, INT-02).

Progres: video 0–90%, chat 90–99%. Checkpoint `video_done` agar coba ulang tidak mengunduh
ulang video yang sudah utuh (file `.part` dilanjutkan oleh yt-dlp). Chat opsional: gagal →
`has_chat = 0`, Job tetap sukses.
"""

import json
from collections.abc import Callable
from pathlib import Path

import structlog
from sqlalchemy import Engine, text

from klipin.config import get_config
from klipin.db.models import utcnow
from klipin.media import chat_replay, ytdlp
from klipin.media import fake as fake_media
from klipin.worker.context import JobContext
from klipin.worker.handlers import register
from klipin.worker.process import JobCancelled

log = structlog.get_logger(__name__)

VIDEO_PCT = 90
MSG_DISK_FULL = "Ruang disk habis. Kosongkan ruang lalu coba lagi."
MSG_CHAT_FAILED = "Chat replay gagal diunduh; skor tetap dihitung tanpa Sinyal Chat."
INSERT_BATCH = 1000


def stream_dir(stream_id: int) -> Path:
    return get_config().klipin_home / "streams" / str(stream_id)


def import_chat(engine: Engine, stream_id: int, path: Path) -> int:
    """Ganti Pesan Chat Stream Sumber dengan isi file (satu transaksi); set `has_chat`."""
    with engine.begin() as conn:
        raw = conn.execute(text("SELECT value FROM settings WHERE key = 'chat_reaction_words'")
                           ).scalar()
        is_reaction = chat_replay.reaction_matcher(_json_list(raw))
        conn.execute(text("DELETE FROM chat_messages WHERE source_stream_id = :s"),
                     {"s": stream_id})
        total, batch = 0, []
        insert = text("INSERT INTO chat_messages (source_stream_id, offset_ms, author, message, "
                      "is_reaction, kind) VALUES (:s, :o, :a, :m, :r, :k)")
        for msg in chat_replay.parse_file(path):
            batch.append({"s": stream_id, "o": msg.offset_ms, "a": msg.author, "m": msg.message,
                          "r": int(is_reaction(msg.message)), "k": msg.kind})
            if len(batch) >= INSERT_BATCH:
                conn.execute(insert, batch)
                total, batch = total + len(batch), []
        if batch:
            conn.execute(insert, batch)
            total += len(batch)
        _set_has_chat(conn, stream_id, total > 0)
    return total


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _set_has_chat(conn, stream_id: int, has_chat: bool) -> None:
    conn.execute(text("UPDATE source_streams SET has_chat = :h, updated_at = :now WHERE id = :s"),
                 {"h": int(has_chat), "now": utcnow(), "s": stream_id})


def clear_chat(engine: Engine, stream_id: int) -> None:
    """Tanpa chat (tidak ada / gagal / Kick): hapus Pesan Chat lama, `has_chat = 0` (BR-002)."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chat_messages WHERE source_stream_id = :s"),
                     {"s": stream_id})
        _set_has_chat(conn, stream_id, False)


def _video(ctx: JobContext, url: str, dest: Path,
           download: Callable[..., ytdlp.DownloadResult]) -> None:
    done = Path(ctx.checkpoint.get("video_path", ""))
    if ctx.checkpoint.get("video_done") and done.is_file():
        ctx.log("video sudah terunduh, lanjut ke chat replay")
        return
    ctx.progress(0, "Mengunduh video")
    try:
        result = download(url, dest, should_cancel=ctx.cancel_event.is_set,
                          on_progress=lambda p: ctx.progress(p * VIDEO_PCT // 100,
                                                             "Mengunduh video"))
    except ytdlp.YtdlpError as e:
        ctx.log(f"yt-dlp: {e.detail[:500]}")
        if "No space left" in e.detail or "Errno 28" in e.detail:
            raise RuntimeError(MSG_DISK_FULL) from e
        raise
    with ctx.engine.begin() as conn:
        conn.execute(text(
            "UPDATE source_streams SET video_path = :p, video_width = :w, video_height = :h, "
            "video_fps = :f, updated_at = :now WHERE id = :s"),
            {"p": str(result.path), "w": result.width, "h": result.height, "f": result.fps,
             "now": utcnow(), "s": ctx.source_stream_id})
    ctx.save_checkpoint({**ctx.checkpoint, "video_done": True, "video_path": str(result.path)})


def _chat(ctx: JobContext, url: str, platform: str, dest: Path,
          fetch_chat: Callable[..., Path | None]) -> None:
    if platform != "youtube":  # VOD Kick tidak punya chat lampau (INT-03)
        clear_chat(ctx.engine, ctx.source_stream_id)
        return
    ctx.progress(VIDEO_PCT, "Mengunduh chat replay")
    try:
        path = fetch_chat(url, dest, should_cancel=ctx.cancel_event.is_set)
        if path is None:
            clear_chat(ctx.engine, ctx.source_stream_id)
            ctx.log("video tanpa chat replay")
            return
        count = import_chat(ctx.engine, ctx.source_stream_id, path)
    except JobCancelled:
        raise
    except Exception:
        log.exception("chat replay gagal", stream_id=ctx.source_stream_id)
        ctx.log(MSG_CHAT_FAILED)
        clear_chat(ctx.engine, ctx.source_stream_id)
        return
    ctx.log(f"chat replay: {count} pesan")


def run(ctx: JobContext, *,
        download: Callable[..., ytdlp.DownloadResult] | None = None,
        fetch_chat: Callable[..., Path | None] | None = None) -> None:
    with ctx.engine.connect() as conn:
        url, platform = conn.execute(text(
            "SELECT source_url, platform FROM source_streams WHERE id = :s"),
            {"s": ctx.source_stream_id}).one()
    dest = stream_dir(ctx.source_stream_id)
    _video(ctx, url, dest, download or ytdlp.download_vod)
    _chat(ctx, url, platform, dest, fetch_chat or ytdlp.download_live_chat)
    ctx.progress(100, "Selesai")


@register("download")
def handle(ctx: JobContext) -> None:
    if get_config().klipin_providers == "fake":  # fixture lokal, tanpa jaringan
        run(ctx, download=fake_media.download_vod, fetch_chat=fake_media.download_live_chat)
        return
    run(ctx)
