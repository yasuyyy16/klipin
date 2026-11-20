import pytest

from klipin.db.migrate import upgrade
from klipin.db.session import make_engine


@pytest.fixture
def engine(tmp_path):
    """Database baru di KLIPIN_HOME sementara, sudah di-upgrade ke head."""
    eng = make_engine(tmp_path / "home")
    upgrade(eng)
    yield eng
    eng.dispose()
