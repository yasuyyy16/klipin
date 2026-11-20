import logging

import keyring
import pytest
import structlog
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from sqlalchemy.orm import Session

from klipin import secrets
from klipin.api.app import create_app
from klipin.api.deps import get_db, get_db_engine
from klipin.config import get_config
from klipin.db.migrate import upgrade
from klipin.db.session import make_engine
from klipin.logging import setup_logging

TOKEN = "tok-uji-123"
PORT = 8765
AUTH = {"Host": f"127.0.0.1:{PORT}", "X-Klipin-Token": TOKEN}


@pytest.fixture
def engine(tmp_path):
    """Database baru di KLIPIN_HOME sementara, sudah di-upgrade ke head."""
    eng = make_engine(tmp_path / "home")
    upgrade(eng)
    yield eng
    eng.dispose()


class MemoryKeyring(KeyringBackend):
    """Keyring di memori agar tes tidak menyentuh Credential Manager/Keychain asli."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError(username)
        del self.store[(service, username)]


@pytest.fixture
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """KLIPIN_HOME sementara + penyedia palsu + .env sementara + log ke file sementara."""
    path = tmp_path / "home"
    monkeypatch.setenv("KLIPIN_HOME", str(path))
    monkeypatch.setenv("KLIPIN_PROVIDERS", "fake")
    monkeypatch.setattr(secrets, "ENV_FILE", tmp_path / ".env")
    get_config.cache_clear()
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    setup_logging(get_config(), "test")
    yield path
    for h in root.handlers:
        h.close()
    root.handlers[:], level = saved
    root.setLevel(level)
    structlog.reset_defaults()
    get_config.cache_clear()


@pytest.fixture
def api(engine, home, memory_keyring, tmp_path):
    """TestClient untuk app lengkap dengan DB sementara; header AUTH sudah benar."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body></body></html>")
    app = create_app(token=TOKEN, dist_dir=dist, port=PORT)

    def _db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_engine] = lambda: engine
    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}", headers=AUTH,
                        raise_server_exceptions=False)
    yield client
    client.close()


def log_text(home_path) -> str:
    for h in logging.getLogger().handlers:
        h.flush()
    path = home_path / "logs" / "klipin.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""
