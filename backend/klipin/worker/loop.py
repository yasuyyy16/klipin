import sqlite3
import time

import structlog

from klipin.config import get_config
from klipin.db.backup import daily_backup

log = structlog.get_logger(__name__)
BACKUP_CHECK_S = 60


def run() -> int:
    # shortcut: belum mengambil Job; loop klaim/heartbeat dibuat di T-014.
    log.info("worker berjalan (kerangka)")
    home = get_config().klipin_home
    next_backup_check = 0.0
    while True:
        if time.monotonic() >= next_backup_check:
            try:
                daily_backup(home)
            except (OSError, sqlite3.Error):
                log.exception("backup harian gagal")
            next_backup_check = time.monotonic() + BACKUP_CHECK_S
        time.sleep(1)
