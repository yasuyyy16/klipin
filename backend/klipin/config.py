"""Konfigurasi dari env (04-arsitektur.md §8.2); file `.env` di root repo ikut dibaca."""

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_ignore_empty=True, extra="ignore"
    )

    klipin_home: Path = Path.home() / "Klipin"
    klipin_port: int = Field(8765, ge=1, le=65535)
    klipin_host: Annotated[list[str], NoDecode] = ["127.0.0.1", "::1"]
    klipin_ffmpeg_path: Path | None = None
    klipin_max_heavy_jobs: int = Field(1, ge=1)
    klipin_transcriber: Literal["deepgram", "assemblyai"] = "deepgram"
    klipin_llm_provider: Literal["anthropic"] = "anthropic"
    transcriber_api_key: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: SecretStr | None = None
    meta_app_id: str | None = None
    meta_app_secret: SecretStr | None = None
    klipin_oauth_redirect_base: str = "http://localhost:8765"
    klipin_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    klipin_providers: Literal["real", "fake"] = "real"

    @field_validator("klipin_host", mode="before")
    @classmethod
    def _split_hosts(cls, v: object) -> object:
        return [h.strip() for h in v.split(",") if h.strip()] if isinstance(v, str) else v

    @field_validator("klipin_host")
    @classmethod
    def _loopback_only(cls, hosts: list[str]) -> list[str]:
        # BR-012: server hanya boleh bind ke alamat loopback.
        if not hosts or not all(ipaddress.ip_address(h).is_loopback for h in hosts):
            raise ValueError("KLIPIN_HOST hanya boleh berisi alamat loopback (127.0.0.1, ::1)")
        return hosts


@lru_cache
def get_config() -> Config:
    return Config()
