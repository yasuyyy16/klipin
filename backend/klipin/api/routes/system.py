from dataclasses import asdict

from fastapi import APIRouter

from klipin import system
from klipin.api.errors import ApiError
from klipin.config import get_config
from klipin.db.backup import backup_dir
from klipin.doctor import run_checks

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health")
def health() -> dict:
    """Setara `klipin doctor`, tanpa cek port (port sedang dipakai server ini sendiri)."""
    cfg = get_config()
    checks = [asdict(c) for c in run_checks(cfg, include_port=False)]
    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "home": str(cfg.klipin_home), "backup_dir": str(backup_dir(cfg.klipin_home))}


@router.post("/update-ytdlp")
def update_ytdlp() -> dict:
    try:
        return system.update_ytdlp()
    except system.UpdateError as exc:
        raise ApiError(502, "UPSTREAM_ERROR", str(exc)) from exc
