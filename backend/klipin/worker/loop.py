import time

import structlog

log = structlog.get_logger(__name__)


def run() -> int:
    # shortcut: belum mengambil Job; loop klaim/heartbeat dibuat di T-014.
    log.info("worker berjalan (kerangka)")
    while True:
        time.sleep(1)
