import json
import logging

import pytest
import structlog

from klipin.config import Config
from klipin.logging import MASK, mask_secrets, setup_logging

SECRETS = [
    "sk-ant-api03-AbCdEf1234567890_xyz-QRS",
    "GOCSPX-abcdefghijklmnop1234",
    "ya29.a0AfH6SMBxyz123456789",
    "1//0gAbCdEfGhIjKlMnOpQrStUv",
    "EAAGm0PX4ZCpsBAKZCZBabcdefghijk123",
    "act.abcdefghijklmnopqrstuvwxyz123",
    "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",  # gaya key Deepgram (40 hex)
]


@pytest.mark.parametrize("secret", SECRETS)
def test_known_key_shapes_masked(secret):
    out = mask_secrets(f"memanggil penyedia dengan {secret} gagal")
    assert secret not in out
    assert MASK in out


@pytest.mark.parametrize(
    "text, leaked",
    [
        ("api_key=hunter2-plain", "hunter2-plain"),
        ('{"llm_api_key": "rahasia-pendek"}', "rahasia-pendek"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("X-Klipin-Token: tok_ABC123xyz", "tok_ABC123xyz"),
        ("GET /api/v1/events?t=SesiAcak_123-xyz HTTP/1.1", "SesiAcak_123-xyz"),
        ("refresh_token=1abc&client_secret=zz9", "zz9"),
    ],
)
def test_named_values_masked(text, leaked):
    assert leaked not in mask_secrets(text)


def test_plain_text_untouched():
    text = "Job download 12 selesai dalam 3.5 detik, 1080p"
    assert mask_secrets(text) == text


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    yield
    for h in root.handlers:
        h.close()
    root.handlers[:], level = saved
    root.setLevel(level)
    structlog.reset_defaults()


def test_log_file_created_and_masked(tmp_path, restore_root_logger):
    cfg = Config(_env_file=None, klipin_home=tmp_path)
    setup_logging(cfg, "test")
    log = structlog.get_logger("klipin.test")
    log.info("tes koneksi", api_key="sk-ant-api03-RahasiaSekali1234567", job_id=7)
    logging.getLogger("uvicorn.access").warning("GET /api/v1/events?t=TokenSesi99 200")
    for h in logging.getLogger().handlers:
        h.flush()

    lines = (tmp_path / "logs" / "klipin.log").read_text(encoding="utf-8").splitlines()
    records = [json.loads(ln) for ln in lines]
    assert records[0]["event"] == "tes koneksi"
    assert records[0]["job_id"] == 7
    assert records[0]["process"] == "test"
    text = "\n".join(lines)
    assert "RahasiaSekali" not in text
    assert "TokenSesi99" not in text
