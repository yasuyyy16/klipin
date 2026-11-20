"""Backup klipin.db (NFR-010): harian, simpan 7 terakhir, plus sebelum setiap migrasi."""

import sqlite3
from datetime import datetime
from pathlib import Path

import structlog
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from klipin.db.migrate import alembic_config, upgrade
from klipin.db.session import db_path

KEEP = 7
log = structlog.get_logger(__name__)


def backup_dir(home: Path) -> Path:
    return home / "backups"


def _copy_db(src: Path, dest: Path) -> None:
    tmp = dest.with_suffix(".tmp")
    s, d = sqlite3.connect(src), sqlite3.connect(tmp)
    try:
        s.backup(d)  # online backup API: aman walau API/Worker sedang menulis
    finally:
        d.close()
        s.close()
    tmp.replace(dest)


def _rotate(folder: Path, pattern: str) -> None:
    for old in sorted(folder.glob(pattern))[:-KEEP]:
        old.unlink()


def daily_backup(home: Path, now: datetime | None = None) -> Path | None:
    """Buat backup hari ini jika belum ada. Mengembalikan path backup baru, atau None."""
    src = db_path(home)
    if not src.exists():
        return None
    folder = backup_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"klipin-{(now or datetime.now()):%Y%m%d}.db"
    if dest.exists():
        return None
    _copy_db(src, dest)
    _rotate(folder, "klipin-[0-9]*.db")
    log.info("backup harian dibuat", path=str(dest))
    return dest


def _needs_upgrade(engine: Engine) -> bool:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision() != head


def prepare_database(engine: Engine, home: Path, now: datetime | None = None) -> None:
    """Migrasi ke head; DB yang sudah ada dicadangkan dulu sebelum dimigrasi."""
    src = db_path(home)
    if src.exists() and src.stat().st_size > 0 and _needs_upgrade(engine):
        folder = backup_dir(home)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"klipin-premigrate-{(now or datetime.now()):%Y%m%d-%H%M%S}.db"
        _copy_db(src, dest)
        _rotate(folder, "klipin-premigrate-*.db")
        log.info("backup sebelum migrasi dibuat", path=str(dest))
    upgrade(engine)
