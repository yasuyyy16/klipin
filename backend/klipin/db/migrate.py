import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)


def sql_statements(path: Path) -> list[str]:
    """Pecah file SQL per pernyataan (driver sqlite3 menolak banyak pernyataan sekaligus)."""
    parts = re.split(r";[ \t]*(?:--[^\n]*)?\n", path.read_text(encoding="utf-8"))
    return [p for p in parts if re.sub(r"--[^\n]*", "", p).strip()]


def execute_sql_file(path: Path) -> None:
    """Dipanggil dari dalam migrasi Alembic."""
    from alembic import op

    conn = op.get_bind()
    for stmt in sql_statements(path):
        conn.exec_driver_sql(stmt)
