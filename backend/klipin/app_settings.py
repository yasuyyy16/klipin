"""Pengaturan non-rahasia di tabel `settings` (kunci 05-database.md §6.2)."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select, text
from sqlalchemy.orm import Session

from klipin.db.models import Setting


def load_all(session: Session) -> dict[str, Any]:
    return {row.key: row.value for row in session.scalars(select(Setting))}


def get(session: Session, key: str) -> Any:
    row = session.get(Setting, key)
    return None if row is None else row.value


def output_dir(home: Path, value: str) -> Path:
    """`output_dir` boleh relatif terhadap KLIPIN_HOME (seed: "output")."""
    path = Path(value)
    return path if path.is_absolute() else home / path


def value(conn: Connection, key: str, default: Any = None) -> Any:
    """Baca satu kunci lewat Connection (dipakai Worker/handler yang tidak memakai Session)."""
    raw = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).scalar()
    try:
        return json.loads(raw) if raw is not None else default
    except ValueError:
        return default
