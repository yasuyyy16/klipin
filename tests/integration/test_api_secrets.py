"""T-012: rahasia di keyring + fallback .env, endpoint secrets. TC-042."""

import keyring
import pytest
from keyring.backends import fail

from klipin import secrets
from tests.conftest import log_text

KEY = "sk-ant-api03-RahasiaUjiPanjang-ABCDEFG9f3c"


def test_tc042_put_then_get_settings_only_masked(api, home, memory_keyring):
    resp = api.put("/api/v1/secrets/llm_api_key", json={"value": KEY})
    assert resp.status_code == 200
    assert resp.json() == {"name": "llm_api_key", "set": True, "masked": "…9f3c"}

    settings = api.get("/api/v1/settings")
    assert settings.status_code == 200
    assert settings.json()["secrets"] == {
        "transcriber_api_key": {"set": False, "masked": None},
        "llm_api_key": {"set": True, "masked": "…9f3c"},
    }
    assert KEY not in resp.text + settings.text
    assert memory_keyring.store[("klipin", "llm_api_key")] == KEY
    assert not secrets.ENV_FILE.exists()  # keyring tersedia: tidak menulis .env
    assert KEY not in log_text(home)


def test_delete_secret(api, memory_keyring):
    api.put("/api/v1/secrets/transcriber_api_key", json={"value": KEY})
    resp = api.delete("/api/v1/secrets/transcriber_api_key")
    assert resp.json() == {"name": "transcriber_api_key", "set": False, "masked": None}
    assert memory_keyring.store == {}


def test_env_fallback_when_keyring_unavailable(api):
    keyring.set_keyring(fail.Keyring())
    assert api.put("/api/v1/secrets/transcriber_api_key", json={"value": KEY}).status_code == 200
    assert f"TRANSCRIBER_API_KEY={KEY}" in secrets.ENV_FILE.read_text(encoding="utf-8")
    body = api.get("/api/v1/settings").json()
    assert body["storage"] == {"keyring_available": False}  # pemicu banner peringatan
    assert body["secrets"]["transcriber_api_key"]["masked"] == "…9f3c"
    api.delete("/api/v1/secrets/transcriber_api_key")
    assert "TRANSCRIBER_API_KEY" not in secrets.ENV_FILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["", "   ", "ada spasi", "baris\nbaru", "x" * 513])
def test_invalid_secret_value_rejected(api, value):
    resp = api.put("/api/v1/secrets/llm_api_key", json={"value": value})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_secret_name_rejected(api):
    assert api.put("/api/v1/secrets/github_token", json={"value": KEY}).status_code == 400


def test_connection_test_needs_secret(api):
    resp = api.post("/api/v1/secrets/transcriber_api_key/test")
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "SECRET_MISSING",
        "message": "API key transkripsi belum diisi atau tidak valid. Buka Pengaturan."}


def test_connection_test_with_fake_provider(api):
    api.put("/api/v1/secrets/llm_api_key", json={"value": KEY})
    resp = api.post("/api/v1/secrets/llm_api_key/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["provider"] == "anthropic"
    assert KEY not in resp.text


def test_connection_test_failure_from_fake_provider(api):
    api.put("/api/v1/secrets/transcriber_api_key", json={"value": "invalid-key-0000"})
    body = api.post("/api/v1/secrets/transcriber_api_key/test").json()
    assert body == {"ok": False, "provider": "deepgram", "latency_ms": None,
                    "error": "401 invalid api key"}


def test_get_settings_has_every_key(api, home):
    body = api.get("/api/v1/settings").json()
    assert {"score_weights", "llm_models", "manual_upload_urls", "secrets", "storage"} <= set(body)
    assert body["output_dir"] == str(home / "output")
