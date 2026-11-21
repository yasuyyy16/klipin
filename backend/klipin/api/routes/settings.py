from fastapi import APIRouter
from sqlalchemy import select, text

from klipin import app_settings, secrets, usage
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.settings import SettingsPatchRequest
from klipin.config import get_config
from klipin.db.models import Setting, SubtitleStyle, utcnow

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
# Kunci yang boleh JSON null: confirm_usage_over_min null = konfirmasi pemakaian mati (FR-022).
NULLABLE = {"confirm_usage_over_min"}


@router.get("")
def get_settings(db: DbSession) -> dict:
    data = app_settings.load_all(db)
    data["output_dir"] = str(app_settings.output_dir(get_config().klipin_home, data["output_dir"]))
    data["secrets"] = secrets.summary()
    data["storage"] = {"keyring_available": secrets.keyring_available()}
    data["pricing_links"] = usage.PRICING_LINKS  # tautan halaman harga resmi (FR-022)
    return data


@router.patch("")
def patch_settings(body: SettingsPatchRequest, db: DbSession) -> dict:
    changes = body.model_dump(exclude_unset=True)
    nulls = {k: "Wajib diisi." for k, v in changes.items() if v is None and k not in NULLABLE}
    if nulls:
        raise ApiError(400, "VALIDATION_ERROR", "Input tidak valid.", nulls)
    style = changes.get("default_subtitle_style")
    if style is not None and db.scalar(
            select(SubtitleStyle.id).where(SubtitleStyle.name == style)) is None:
        raise ApiError(400, "VALIDATION_ERROR", "Gaya Subtitle tidak ditemukan.",
                       {"default_subtitle_style": "Gaya Subtitle tidak ditemukan."})
    for key, value in changes.items():
        if value is None:  # JSON null (kolom value NOT NULL, jadi bukan NULL SQL)
            db.execute(text("UPDATE settings SET value = 'null', updated_at = :now "
                            "WHERE key = :k"), {"k": key, "now": utcnow()})
            continue
        row = db.get(Setting, key)
        if row is None:  # kunci seed hilang (DB lama): buat ulang
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_settings(db)
