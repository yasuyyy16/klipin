"""Pemilihan penyedia transkripsi (ADR-003).

Urutan: `KLIPIN_PROVIDERS=fake` → `FakeTranscriber`; selain itu Pengaturan
`transcriber_provider`, dan env `KLIPIN_TRANSCRIBER` hanya bila Pengaturan kosong
(keputusan pemilik 2026-11-21). API key dicek di sini, sebelum audio apa pun dikirim (TC-014).
"""

import json

from sqlalchemy import Engine, text

from klipin import secrets
from klipin.config import get_config
from klipin.providers.transcriber.base import (
    AudioChunk,
    Transcriber,
    TranscriberAuthError,
    TranscriberBadAudioError,
    TranscriberError,
    TranscriberTransientError,
    TranscriptionResult,
    Utterance,
    Word,
)
from klipin.providers.transcriber.fake import FakeTranscriber

__all__ = [
    "AudioChunk", "FakeTranscriber", "Transcriber", "TranscriberAuthError",
    "TranscriberBadAudioError", "TranscriberError", "TranscriberTransientError",
    "TranscriptionResult", "Utterance", "Word", "get_transcriber", "provider_name",
]

SECRET = "transcriber_api_key"


def provider_name(engine: Engine) -> str:
    with engine.connect() as conn:
        raw = conn.execute(text("SELECT value FROM settings WHERE key = 'transcriber_provider'")
                           ).scalar()
    try:
        value = json.loads(raw) if raw else None
    except ValueError:
        value = None
    return value or get_config().klipin_transcriber


def get_transcriber(engine: Engine) -> Transcriber:
    key = secrets.get_secret(SECRET)
    if not key:
        raise TranscriberAuthError("API key kosong")
    if get_config().klipin_providers == "fake":
        return FakeTranscriber(api_key=key)
    name = provider_name(engine)
    # shortcut: adapter Deepgram (T-028) dan AssemblyAI (T-029) belum ada.
    raise TranscriberError(f"Penyedia transkripsi {name} belum tersedia di versi ini.")
