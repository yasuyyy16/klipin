"""Engine & sesi SQLite (WAL, foreign_keys=ON, busy_timeout=5000) di {KLIPIN_HOME}/klipin.db."""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from klipin.config import get_config


def db_path(home: Path) -> Path:
    return home / "klipin.db"


def make_engine(home: Path) -> Engine:
    home.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path(home)}")

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA journal_mode = WAL")
        cur.execute("PRAGMA busy_timeout = 5000")
        cur.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_config().klipin_home)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)
