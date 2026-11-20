"""T-008: skema dari migrasi Alembic + constraint 05-database.md §5."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from klipin.db.migrate import upgrade
from klipin.db.models import Base, include_in_autogenerate

TABLES = {
    "layout_presets", "channels", "source_streams", "subtitle_styles", "live_markers", "clips",
    "upload_accounts", "uploads", "jobs", "transcription_chunks", "transcript_segments",
    "transcript_words", "chat_messages", "highlight_windows", "cam_regions", "settings",
}


def run(engine, sql, *params):
    with engine.begin() as conn:
        return conn.exec_driver_sql(sql, params).fetchall() if sql.startswith("SELECT") \
            else conn.exec_driver_sql(sql, params)


@pytest.fixture
def base_rows(engine):
    """Preset, gaya, Kanal, Stream Sumber minimal untuk FK."""
    run(engine, "INSERT INTO layout_presets (id, code, name) VALUES (1, 'gaming', 'G')")
    run(engine, "INSERT INTO subtitle_styles (id, name, mode) VALUES (1, 'S', 'sentence')")
    run(engine, "INSERT INTO channels (id, platform, name) VALUES (1, 'youtube', 'Kanal')")
    run(engine, "INSERT INTO source_streams (id, channel_id, source_type, platform, source_url, "
                "title) VALUES (1, 1, 'vod_url', 'youtube', 'https://youtu.be/x', 'Stream')")
    return engine


def insert_clip(engine, status, start_ms, end_ms, clip_id=None):
    run(engine, "INSERT INTO clips (id, source_stream_id, origin, status, start_ms, end_ms, "
                "layout_preset_id, subtitle_style_id, output_video_path) "
                "VALUES (?, 1, 'auto', ?, ?, ?, 1, 1, ?)",
        clip_id, status, start_ms, end_ms, "out.mp4" if status == "rendered" else None)


def test_upgrade_from_zero_creates_all_tables(engine):
    assert set(inspect(engine).get_table_names()) >= TABLES


def test_upgrade_again_is_noop(engine):
    upgrade(engine)


def test_pragmas(engine):
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000


def test_models_match_migrations(engine):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"include_object": include_in_autogenerate})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


@pytest.mark.parametrize(("status", "dur_ms", "ok"), [
    ("candidate", 5_000, True),     # kandidat boleh di luar 15-90 detik
    ("rejected", 120_000, True),
    ("approved", 14_999, False),
    ("approved", 15_000, True),
    ("approved", 90_000, True),
    ("approved", 90_001, False),
    ("rendered", 10_000, False),
])
def test_clip_duration_check(base_rows, status, dur_ms, ok):
    if ok:
        insert_clip(base_rows, status, 1_000, 1_000 + dur_ms)
    else:
        with pytest.raises(IntegrityError):
            insert_clip(base_rows, status, 1_000, 1_000 + dur_ms)


def test_br009_one_active_upload_per_platform(base_rows):
    insert_clip(base_rows, "rendered", 0, 30_000, clip_id=1)
    add = ("INSERT INTO uploads (clip_id, platform, mode, status, title) "
           "VALUES (1, ?, 'manual', ?, 'Judul')")
    run(base_rows, add, "youtube", "pending")
    run(base_rows, add, "tiktok", "pending")  # platform lain boleh
    with pytest.raises(IntegrityError):
        run(base_rows, add, "youtube", "pending")
    with pytest.raises(IntegrityError):
        run(base_rows, add, "youtube", "uploaded")


def test_manual_upload_cannot_be_uploading(base_rows):
    insert_clip(base_rows, "rendered", 0, 30_000, clip_id=1)
    with pytest.raises(IntegrityError):
        run(base_rows, "INSERT INTO uploads (clip_id, platform, mode, status) "
                       "VALUES (1, 'tiktok', 'manual', 'uploading')")


@pytest.mark.parametrize(("job_type", "purpose", "preview_at", "clip", "ok"), [
    ("render", "final", None, 1, True),
    ("render", "preview", 5_000, 1, True),
    ("render", "preview", None, 1, False),    # preview wajib preview_at_ms
    ("download", "preview", 0, None, False),  # preview hanya untuk render
    ("render", "draft", None, 1, False),      # nilai purpose tidak dikenal
    ("render", "final", None, None, False),   # render wajib clip_id
])
def test_job_purpose_check(base_rows, job_type, purpose, preview_at, clip, ok):
    insert_clip(base_rows, "approved", 0, 30_000, clip_id=1)
    sql = ("INSERT INTO jobs (job_type, source_stream_id, clip_id, purpose, preview_at_ms) "
           "VALUES (?, 1, ?, ?, ?)")
    if ok:
        run(base_rows, sql, job_type, clip, purpose, preview_at)
    else:
        with pytest.raises(IntegrityError):
            run(base_rows, sql, job_type, clip, purpose, preview_at)


REGION = ("INSERT INTO cam_regions (channel_id, source_stream_id, clip_id, role, x, y, w, h) "
          "VALUES (?, ?, ?, ?, 0.1, 0.1, 0.3, 0.3)")


@pytest.mark.parametrize(("owners", "ok"), [
    ((1, None, None), True),
    ((None, 1, None), True),
    ((None, None, None), False),  # tanpa pemilik
    ((1, 1, None), False),        # dua pemilik
])
def test_cam_region_single_owner(base_rows, owners, ok):
    if ok:
        run(base_rows, REGION, *owners, "cam")
    else:
        with pytest.raises(IntegrityError):
            run(base_rows, REGION, *owners, "cam")


def test_cam_region_one_per_role_per_owner(base_rows):
    run(base_rows, REGION, None, 1, None, "cam")
    run(base_rows, REGION, None, 1, None, "content")
    with pytest.raises(IntegrityError):
        run(base_rows, REGION, None, 1, None, "cam")


def test_cam_region_must_fit_frame(base_rows):
    with pytest.raises(IntegrityError):
        run(base_rows, "INSERT INTO cam_regions (source_stream_id, role, x, y, w, h) "
                       "VALUES (1, 'cam', 0.8, 0.1, 0.3, 0.3)")


@pytest.mark.parametrize("sql", [
    "INSERT INTO channels (platform, name) VALUES ('twitch', 'x')",
    "INSERT INTO source_streams (source_type, platform, title) VALUES ('vod_url', 'youtube', 'x')",
    ("INSERT INTO source_streams (source_type, platform, title) "
     "VALUES ('local_file', 'youtube', 'x')"),
    "INSERT INTO settings (key, value) VALUES ('k', 'bukan json')",
    "INSERT INTO jobs (job_type, source_stream_id, status) VALUES ('download', 1, 'paused')",
    "INSERT INTO jobs (job_type, source_stream_id, progress_pct) VALUES ('download', 1, 101)",
    "INSERT INTO subtitle_styles (name, mode, primary_color) VALUES ('x', 'sentence', 'white')",
    "INSERT INTO jobs (job_type, source_stream_id) VALUES ('download', 999)",  # FK
])
def test_invalid_rows_rejected(base_rows, sql):
    with pytest.raises(IntegrityError):
        run(base_rows, sql)


def test_delete_stream_cascades(base_rows):
    insert_clip(base_rows, "candidate", 0, 30_000, clip_id=1)
    run(base_rows, "INSERT INTO jobs (job_type, source_stream_id) VALUES ('download', 1)")
    run(base_rows, "DELETE FROM source_streams WHERE id = 1")
    assert run(base_rows, "SELECT count(*) FROM clips") == [(0,)]
    assert run(base_rows, "SELECT count(*) FROM jobs") == [(0,)]
