"""API key di keyring OS (service `klipin`); fallback `.env` jika keyring tidak ada (ADR-007).

Nilai rahasia tidak pernah dikembalikan utuh ke API dan tidak pernah dicatat di log.
"""

import re

import keyring
from keyring.backends import fail, null
from keyring.errors import KeyringError, PasswordDeleteError

from klipin.config import ROOT_DIR, Config

SERVICE = "klipin"
NAMES = ("transcriber_api_key", "llm_api_key")
ENV_FILE = ROOT_DIR / ".env"
VALID_VALUE = re.compile(r"^[!-~]{1,512}$")  # ASCII terlihat, tanpa spasi/baris baru


def keyring_available() -> bool:
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001 - backend keyring bisa melempar error jenis apa saja
        return False
    return not isinstance(backend, (fail.Keyring, null.Keyring))


def _from_env(name: str) -> str | None:
    secret = getattr(Config(_env_file=ENV_FILE), name)
    return secret.get_secret_value() if secret else None


def get_secret(name: str) -> str | None:
    if keyring_available():
        try:
            value = keyring.get_password(SERVICE, name)
        except KeyringError:
            value = None
        if value:
            return value
    return _from_env(name)


def _write_env(name: str, value: str | None) -> None:
    key = name.upper()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    if value is not None:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_secret(name: str, value: str) -> str:
    """Simpan rahasia; mengembalikan lokasi penyimpanan: `keyring` atau `env`."""
    if keyring_available():
        keyring.set_password(SERVICE, name, value)
        return "keyring"
    _write_env(name, value)
    return "env"


def delete_secret(name: str) -> None:
    if keyring_available():
        try:
            keyring.delete_password(SERVICE, name)
        except PasswordDeleteError:
            pass
    if ENV_FILE.exists():
        _write_env(name, None)


def mask(value: str | None) -> str | None:
    if not value:
        return None
    return "…" + value[-4:] if len(value) > 8 else "…"


def summary() -> dict[str, dict]:
    result = {}
    for name in NAMES:
        value = get_secret(name)
        result[name] = {"set": bool(value), "masked": mask(value)}
    return result
