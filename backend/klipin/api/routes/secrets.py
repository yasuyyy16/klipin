from typing import Literal

from fastapi import APIRouter

from klipin import app_settings, secrets
from klipin.api.deps import DbSession
from klipin.api.errors import ApiError
from klipin.api.schemas.secrets import SecretPutRequest, SecretResponse, SecretTestResponse
from klipin.providers.connection import test_connection

router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])
SecretName = Literal["transcriber_api_key", "llm_api_key"]
PROVIDER_KEY = {"transcriber_api_key": "transcriber_provider", "llm_api_key": "llm_provider"}
MISSING_MESSAGE = {
    "transcriber_api_key": "API key transkripsi belum diisi atau tidak valid. Buka Pengaturan.",
    "llm_api_key": "API key LLM belum diisi atau tidak valid. Buka Pengaturan.",
}


def _response(name: str) -> SecretResponse:
    value = secrets.get_secret(name)
    return SecretResponse(name=name, set=bool(value), masked=secrets.mask(value))


@router.put("/{name}")
def put_secret(name: SecretName, body: SecretPutRequest) -> SecretResponse:
    value = body.value.strip()
    if not secrets.VALID_VALUE.match(value):
        raise ApiError(400, "VALIDATION_ERROR", "API key tidak valid.",
                       {"value": "Isi API key tanpa spasi, maksimal 512 karakter."})
    secrets.set_secret(name, value)
    return _response(name)


@router.delete("/{name}")
def delete_secret(name: SecretName) -> SecretResponse:
    secrets.delete_secret(name)
    return _response(name)


@router.post("/{name}/test")
def test_secret(name: SecretName, db: DbSession) -> SecretTestResponse:
    value = secrets.get_secret(name)
    if not value:
        raise ApiError(409, "SECRET_MISSING", MISSING_MESSAGE[name])
    provider = app_settings.get(db, PROVIDER_KEY[name]) or ""
    return SecretTestResponse(**test_connection(provider, value))
