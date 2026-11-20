import time


def run() -> int:
    # shortcut: belum mengambil Job; loop klaim/heartbeat dibuat di T-014.
    print("Worker berjalan (kerangka).", flush=True)
    while True:
        time.sleep(1)
