"""Pengaturan non-rahasia di tabel `settings` (kunci 05-database.md §6.2)."""

from pathlib import Path
from typing import Any

from sqlalchemy import select
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
