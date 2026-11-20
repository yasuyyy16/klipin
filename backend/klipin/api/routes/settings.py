from fastapi import APIRouter

from klipin import app_settings, secrets
from klipin.api.deps import DbSession
from klipin.config import get_config

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
def get_settings(db: DbSession) -> dict:
    data = app_settings.load_all(db)
    data["output_dir"] = str(app_settings.output_dir(get_config().klipin_home, data["output_dir"]))
    data["secrets"] = secrets.summary()
    data["storage"] = {"keyring_available": secrets.keyring_available()}
    return data
