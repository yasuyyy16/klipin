"""T-010: backup harian (simpan 7) + backup sebelum migrasi (NFR-010)."""

import sqlite3
from datetime import datetime, timedelta

from klipin.db.backup import KEEP, backup_dir, daily_backup, prepare_database
from klipin.db.migrate import upgrade
from klipin.db.session import db_path, make_engine


def backups(home, pattern="klipin-[0-9]*.db"):
    return sorted(p.name for p in backup_dir(home).glob(pattern))


def test_daily_backup_once_per_day_and_rotates(engine, tmp_path):
    home = tmp_path / "home"
    day = datetime(2026, 11, 20, 9, 0)
    assert daily_backup(home, day).name == "klipin-20261120.db"
    assert daily_backup(home, day.replace(hour=23)) is None  # hari yang sama: tidak dobel

    for i in range(1, 10):  # majukan jam 9 hari
        daily_backup(home, day + timedelta(days=i))
    names = backups(home)
    assert len(names) == KEEP
    assert names[0] == "klipin-20261123.db"
    assert names[-1] == "klipin-20261129.db"


def test_backup_is_a_valid_copy(engine, tmp_path):
    home = tmp_path / "home"
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE settings SET value = '77' WHERE key = 'score_min_threshold'")
    path = daily_backup(home, datetime(2026, 11, 20))
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute(
            "SELECT value FROM settings WHERE key = 'score_min_threshold'").fetchone() == ("77",)
    conn.close()


def test_no_backup_without_database(tmp_path):
    assert daily_backup(tmp_path / "kosong") is None


def test_backup_before_migration(tmp_path):
    home = tmp_path / "home"
    engine = make_engine(home)
    upgrade(engine, "0001")  # DB lama, belum di head
    prepare_database(engine, home, datetime(2026, 11, 20, 8, 30, 0))
    assert backups(home, "klipin-premigrate-*.db") == ["klipin-premigrate-20261120-083000.db"]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM layout_presets").scalar() == 6
    prepare_database(engine, home)  # sudah di head: tidak ada backup baru
    assert len(backups(home, "klipin-premigrate-*.db")) == 1
    engine.dispose()


def test_fresh_database_not_backed_up(tmp_path):
    home = tmp_path / "home"
    engine = make_engine(home)
    assert not db_path(home).exists()
    prepare_database(engine, home)
    assert not backup_dir(home).exists()
    engine.dispose()
