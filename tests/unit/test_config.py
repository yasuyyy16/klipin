import pytest
from pydantic import ValidationError

from klipin.config import ROOT_DIR, Config

ENV_EXAMPLE = ROOT_DIR / ".env.example"


def _example_names() -> set[str]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    return {ln.split("=", 1)[0] for ln in lines if ln and not ln.startswith("#")}


def test_env_example_lists_every_config_field():
    assert _example_names() == {name.upper() for name in Config.model_fields}


def test_defaults(monkeypatch):
    for name in Config.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    cfg = Config(_env_file=None)
    assert cfg.klipin_port == 8765
    assert cfg.klipin_host == ["127.0.0.1", "::1"]
    assert cfg.klipin_home.name == "Klipin"
    assert cfg.klipin_max_heavy_jobs == 1
    assert cfg.klipin_transcriber == "deepgram"
    assert cfg.klipin_llm_provider == "anthropic"
    assert cfg.klipin_oauth_redirect_base == "http://localhost:8765"
    assert cfg.klipin_log_level == "INFO"
    assert cfg.klipin_providers == "real"


def test_env_example_values_parse_to_defaults():
    assert Config(_env_file=ENV_EXAMPLE).model_dump() == Config(_env_file=None).model_dump()


@pytest.mark.parametrize("hosts", ["0.0.0.0", "127.0.0.1,192.168.1.5", "localhost"])
def test_non_loopback_host_rejected(monkeypatch, hosts):
    monkeypatch.setenv("KLIPIN_HOST", hosts)
    with pytest.raises(ValidationError):
        Config(_env_file=None)


def test_secret_not_in_repr(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-rahasia123")
    assert "rahasia123" not in repr(Config(_env_file=None))
