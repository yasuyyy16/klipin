"""Skema awal: seluruh DDL 05-database.md §5.

Revision ID: 0001
Revises:
"""

from pathlib import Path

from alembic import op

from klipin.db.migrate import execute_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).with_name("0001_schema.sql")
TABLES_REVERSED = [
    "settings", "cam_regions", "highlight_windows", "chat_messages", "transcript_words",
    "transcript_segments", "transcription_chunks", "jobs", "uploads", "upload_accounts",
    "clips", "live_markers", "subtitle_styles", "source_streams", "channels", "layout_presets",
]


def upgrade() -> None:
    execute_sql_file(SQL_FILE)


def downgrade() -> None:
    for table in TABLES_REVERSED:
        op.drop_table(table)
