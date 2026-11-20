import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

app = FastAPI(title="Klipin")

if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="spa")
else:
    logging.getLogger(__name__).warning(
        "frontend/dist tidak ditemukan; jalankan `cd frontend && pnpm build`."
    )
