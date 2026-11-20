"""SSE `GET /api/v1/events` (06-api.md): polling DB tiap 1 detik, `: ping` tiap 15 detik."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Connection, Engine, text

from klipin.api.deps import DbEngine
from klipin.api.errors import ApiError

router = APIRouter(prefix="/api/v1", tags=["events"])
POLL_S = 1.0
PING_S = 15.0
WINDOW_S = 5  # baris yang berubah dalam 5 detik terakhir diperiksa ulang
MAX_CONNECTIONS = 5
_connections = 0

QUERIES = {
    "job": "SELECT id, job_type, status, progress_pct, stage, source_stream_id, clip_id, "
           "awaiting_confirmation, error_message, started_at, finished_at, updated_at FROM jobs "
           "WHERE updated_at >= :since",
    "stream": "SELECT id, status, error_message, updated_at FROM source_streams "
              "WHERE updated_at >= :since",
    "clip": "SELECT id, source_stream_id, origin, status, created_at, updated_at FROM clips "
            "WHERE updated_at >= :since",
    "upload": "SELECT id, clip_id, platform, mode, status, external_url, posted_as_private, "
              "updated_at FROM uploads WHERE updated_at >= :since",
}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ChangeTracker:
    """Mengubah isi tabel menjadi event SSE; hanya perubahan setelah koneksi dibuka."""

    def __init__(self, connected_at: datetime) -> None:
        self.connected_at = _iso(connected_at)
        self.sent: dict[tuple[str, int], tuple] = {}

    def poll(self, conn: Connection, now: datetime) -> list[tuple[str, dict]]:
        since = max(self.connected_at, _iso(now - timedelta(seconds=WINDOW_S)))
        events: list[tuple[str, dict]] = []
        seen: set[tuple[str, int]] = set()
        for kind, sql in QUERIES.items():
            for row in conn.execute(text(sql), {"since": since}).mappings():
                data = dict(row)
                key = (kind, data["id"])
                seen.add(key)
                signature = tuple(data.values())
                if self.sent.get(key) == signature:
                    continue
                first_time = key not in self.sent
                self.sent[key] = signature
                events.append(self._event(conn, kind, data, first_time))
        self.sent = {k: v for k, v in self.sent.items() if k in seen}
        return events

    def _event(self, conn: Connection, kind: str, data: dict,
               first_time: bool) -> tuple[str, dict]:
        data.pop("updated_at")
        if kind == "job":
            data["awaiting_confirmation"] = bool(data["awaiting_confirmation"])
        elif kind == "stream":
            counts = conn.execute(text("SELECT status, count(*) FROM clips "
                                       "WHERE source_stream_id = :id GROUP BY status"),
                                  {"id": data["id"]}).all()
            data["clip_counts"] = dict(counts)
        elif kind == "clip":
            created_at = data.pop("created_at")
            if first_time and created_at >= self.connected_at:
                return "clip.created", data
        elif kind == "upload":
            data["posted_as_private"] = bool(data["posted_as_private"])
        return f"{kind}.updated", data


def _poll(engine: Engine, tracker: ChangeTracker) -> list[tuple[str, dict]]:
    with engine.connect() as conn:  # koneksi baru tiap polling: snapshot WAL terbaru
        return tracker.poll(conn, datetime.now(UTC))


def format_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream(request: Request, engine: Engine) -> AsyncIterator[str]:
    global _connections
    tracker = ChangeTracker(datetime.now(UTC))
    next_ping = time.monotonic() + PING_S
    try:
        yield ": terhubung\n\n"
        while not await request.is_disconnected():
            for event, data in await asyncio.to_thread(_poll, engine, tracker):
                yield format_event(event, data)
            if time.monotonic() >= next_ping:
                yield ": ping\n\n"
                next_ping = time.monotonic() + PING_S
            await asyncio.sleep(POLL_S)
    finally:
        _connections -= 1


@router.get("/events")
async def events(request: Request, engine: DbEngine) -> StreamingResponse:
    global _connections
    if _connections >= MAX_CONNECTIONS:
        raise ApiError(429, "TOO_MANY_CONNECTIONS",
                       "Terlalu banyak tab Klipin terbuka. Tutup tab lain lalu muat ulang.")
    _connections += 1
    return StreamingResponse(_stream(request, engine), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
