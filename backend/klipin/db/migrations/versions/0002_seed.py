"""Data awal: Preset Layout, Gaya Subtitle, dan Pengaturan (05-database.md §6.2).

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

from klipin.db.migrate import execute_sql_file

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).with_name("0002_seed.sql")


def upgrade() -> None:
    execute_sql_file(SQL_FILE)


def downgrade() -> None:
    op.execute("DELETE FROM settings")
    op.execute("DELETE FROM subtitle_styles WHERE is_builtin = 1")
    op.execute("DELETE FROM layout_presets WHERE is_builtin = 1")
