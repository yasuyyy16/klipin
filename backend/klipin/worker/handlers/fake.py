"""Handler palsu (KLIPIN_PROVIDERS=fake) untuk Jenis Job yang belum punya handler asli.

Mensimulasikan kerja bertahap dengan progres dan checkpoint, sehingga pembatalan, coba ulang
(lanjut dari checkpoint), dan tampilan progres bisa diuji tanpa media atau API sungguhan.
"""

import time

from klipin.worker.context import JobContext

STEPS = 20
STEP_S = 0.5


def fake_handler(ctx: JobContext) -> None:
    done = int(ctx.checkpoint.get("steps_done", 0))
    if done:
        ctx.log(f"lanjut dari langkah {done + 1}/{STEPS}")
    for step in range(done, STEPS):
        ctx.progress(step * 100 // STEPS, f"Langkah palsu {step + 1}/{STEPS}")
        time.sleep(STEP_S)
        ctx.check_cancelled()
        ctx.save_checkpoint({"steps_done": step + 1})
    ctx.progress(100, "Selesai")
