"""Yang diterima handler Job: data Job + cara menulis progres, checkpoint, log, dan cek batal."""

import threading
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, text

from klipin.db.models import JsonText, utcnow
from klipin.worker.process import JobCancelled, run_cancellable

LOG_TAIL_MAX = 4000  # CHECK jobs.log_tail
_json = JsonText()


@dataclass
class JobContext:
    engine: Engine
    id: int
    job_type: str
    source_stream_id: int | None
    clip_id: int | None
    upload_id: int | None
    purpose: str
    preview_at_ms: int | None
    scope_start_ms: int | None
    scope_end_ms: int | None
    checkpoint: dict[str, Any]
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def _update(self, sql: str, **params: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(f"UPDATE jobs SET {sql}, updated_at = :now "
                              "WHERE id = :id AND status = 'running'"),
                         {**params, "id": self.id, "now": utcnow()})

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled

    def progress(self, pct: int, stage: str | None = None) -> None:
        self.check_cancelled()
        self._update("progress_pct = :pct, stage = :stage",
                     pct=max(0, min(100, int(pct))), stage=stage)

    def save_checkpoint(self, data: dict[str, Any]) -> None:
        self.checkpoint = data
        self._update("checkpoint = :cp", cp=_json.process_bind_param(data, None))

    def log(self, line: str) -> None:
        with self.engine.begin() as conn:
            current = conn.execute(text("SELECT log_tail FROM jobs WHERE id = :id"),
                                   {"id": self.id}).scalar() or ""
            tail = (current + line.rstrip("\n") + "\n")[-LOG_TAIL_MAX:]
            conn.execute(text("UPDATE jobs SET log_tail = :t WHERE id = :id"),
                         {"t": tail, "id": self.id})

    def run(self, args: list[str], **popen_kwargs: Any) -> int:
        return run_cancellable(args, self.cancel_event, **popen_kwargs)
