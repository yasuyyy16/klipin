"""T-009: seed 05-database.md §6.2 sebagai migrasi data idempoten."""

import json

from klipin.db.migrate import MIGRATIONS_DIR, sql_statements, upgrade

SEED_SQL = MIGRATIONS_DIR / "versions" / "0002_seed.sql"
SETTINGS_KEYS = {
    "score_weights", "score_min_threshold", "chat_delay_ms", "chat_reaction_words",
    "live_segment_seconds", "live_block_minutes", "live_last_n_default_s", "max_heavy_jobs",
    "confirm_usage_over_min", "max_audio_minutes_per_job", "transcriber_provider",
    "llm_provider", "llm_models", "kick_live_chat_enabled", "default_subtitle_style",
    "output_dir", "download_max_height", "upload_default_mode", "caption_templates",
    "upload_platforms_enabled", "manual_upload_urls",
}


def query(engine, sql):
    with engine.connect() as conn:
        return conn.exec_driver_sql(sql).fetchall()


def counts(engine):
    return (
        query(engine, "SELECT count(*) FROM layout_presets")[0][0],
        query(engine, "SELECT count(*) FROM subtitle_styles")[0][0],
        query(engine, "SELECT count(*) FROM settings")[0][0],
    )


def test_seed_present_after_migration(engine):
    presets = query(engine, "SELECT code, is_builtin FROM layout_presets")
    assert sorted(code for code, _ in presets) == sorted(
        ["gaming", "podcast", "irl", "split_two", "center_crop", "custom"])
    assert all(builtin == 1 for _, builtin in presets)

    styles = query(engine, "SELECT name, is_builtin FROM subtitle_styles")
    assert sorted(n for n, _ in styles) == ["Besar Tengah", "Highlight Kata", "Sederhana"]
    assert all(builtin == 1 for _, builtin in styles)

    settings = dict(query(engine, "SELECT key, value FROM settings"))
    assert set(settings) == SETTINGS_KEYS
    values = {k: json.loads(v) for k, v in settings.items()}
    assert round(sum(values["score_weights"].values()), 6) == 1.0  # BR-001
    assert values["llm_models"] == {
        "judge_highlight": None, "translate_lines": None, "write_captions": None}
    assert values["default_subtitle_style"] == "Highlight Kata"


def test_rerun_does_not_duplicate_or_overwrite(engine):
    before = counts(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE settings SET value = '55' WHERE key = 'score_min_threshold'")
        for stmt in sql_statements(SEED_SQL):
            conn.exec_driver_sql(stmt)
    upgrade(engine)
    assert counts(engine) == before == (6, 3, len(SETTINGS_KEYS))
    assert query(engine, "SELECT value FROM settings WHERE key = 'score_min_threshold'") == [
        ("55",)]
