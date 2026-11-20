from fastapi import APIRouter
from sqlalchemy import select

from klipin import app_settings, secrets
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.settings import SettingsPatchRequest
from klipin.config import get_config
from klipin.db.models import Setting, SubtitleStyle

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
def get_settings(db: DbSession) -> dict:
    data = app_settings.load_all(db)
    data["output_dir"] = str(app_settings.output_dir(get_config().klipin_home, data["output_dir"]))
    data["secrets"] = secrets.summary()
    data["storage"] = {"keyring_available": secrets.keyring_available()}
    return data


@router.patch("")
def patch_settings(body: SettingsPatchRequest, db: DbSession) -> dict:
    changes = body.model_dump(exclude_unset=True)
    nulls = {k: "Wajib diisi." for k, v in changes.items() if v is None}
    if nulls:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.", nulls)
    style = changes.get("default_subtitle_style")
    if style is not None and db.scalar(
            select(SubtitleStyle.id).where(SubtitleStyle.name == style)) is None:
        raise ApiError(400, "VALIDATION_ERROR", "Gaya Subtitle tidak ditemukan.",
                       {"default_subtitle_style": "Gaya Subtitle tidak ditemukan."})
    for key, value in changes.items():
        row = db.get(Setting, key)
        if row is None:  # kunci seed hilang (DB lama): buat ulang
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_settings(db)
