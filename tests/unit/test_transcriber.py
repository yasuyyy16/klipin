"""T-026: antarmuka Transcriber, pemilihan penyedia, dan FakeTranscriber deterministik."""

from pathlib import Path

import pytest

from klipin import secrets
from klipin.config import get_config
from klipin.providers import transcriber as tr
from klipin.providers.transcriber import (
    AudioChunk,
    FakeTranscriber,
    TranscriberAuthError,
    TranscriberError,
    TranscriberTransientError,
)

AUDIO = Path("chunk.flac")  # FakeTranscriber tidak membaca file


def chunk(index, start_ms, end_ms, language=None):
    return AudioChunk(AUDIO, index, start_ms, end_ms, language)


def absolute_words(c, result):
    return [(w.start_ms + c.start_ms, w.end_ms + c.start_ms, w.word)
            for u in result.utterances for w in u.words]


# --- pemilihan penyedia -------------------------------------------------------------------

@pytest.fixture
def keyed(engine, home, memory_keyring):
    secrets.set_secret("transcriber_api_key", "kunci-uji")
    return engine


def test_missing_key_fails_before_anything(engine, home, memory_keyring):
    with pytest.raises(TranscriberAuthError) as e:
        tr.get_transcriber(engine)
    assert str(e.value) == "API key transkripsi belum diisi atau tidak valid. Buka Pengaturan."


def test_fake_mode_uses_fake_transcriber(keyed):
    t = tr.get_transcriber(keyed)
    assert isinstance(t, FakeTranscriber)
    assert t.api_key == "kunci-uji"


def test_real_mode_reads_provider_from_settings(keyed, monkeypatch):
    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    monkeypatch.setenv("KLIPIN_TRANSCRIBER", "assemblyai")
    get_config.cache_clear()
    # Pengaturan menang atas env (seed: deepgram)
    assert tr.provider_name(keyed) == "deepgram"
    assert tr.get_transcriber(keyed).name == "deepgram"
    # Pengaturan kosong → env
    with keyed.begin() as conn:
        conn.exec_driver_sql("UPDATE settings SET value = 'null' "
                             "WHERE key = 'transcriber_provider'")
    assert tr.provider_name(keyed) == "assemblyai"
    with pytest.raises(TranscriberError, match="assemblyai belum tersedia"):
        tr.get_transcriber(keyed)


# --- FakeTranscriber ----------------------------------------------------------------------

def test_fake_is_deterministic_and_chunk_relative():
    c = chunk(0, 0, 60_000)
    a = FakeTranscriber().transcribe(c)
    b = FakeTranscriber().transcribe(c)
    assert a == b
    assert a.language == "id"
    words = [w for u in a.utterances for w in u.words]
    assert words[0].start_ms == 0 and words[0].word == "halo"
    starts = [w.start_ms for w in words]
    assert starts == sorted(starts)
    assert all(0 <= w.start_ms < w.end_ms <= 60_000 for w in words)
    assert {w.speaker for w in words} == {"0", "1"}
    assert any(w.confidence < 0.6 for w in words)
    u = a.utterances[1]
    assert (u.start_ms, u.end_ms, u.speaker) == (6000, 11_800, "1")
    assert u.text == "hari ini kita main sampai pagi"


def test_fake_overlap_returns_same_absolute_words():
    """Dua potongan tumpang tindih 2 detik: kata di zona itu muncul di keduanya (untuk dijahit)."""
    first, second = chunk(0, 0, 600_000), chunk(1, 598_000, 1_200_000)
    t = FakeTranscriber()
    a = absolute_words(first, t.transcribe(first))
    b = absolute_words(second, t.transcribe(second))
    overlap_a = [w for w in a if w[0] >= 598_000]
    overlap_b = [w for w in b if w[1] <= 600_000]
    assert overlap_a and overlap_a == overlap_b
    assert all(w[0] >= 598_000 for w in b)
    assert b[0][0] - 598_000 < 2000  # potongan kedua dimulai di zona tumpang tindih


def test_fake_silence_gives_no_words():
    t = FakeTranscriber(silent_ranges=[(0, 120_000)])
    assert t.transcribe(chunk(0, 0, 120_000)).utterances == []
    partial = t.transcribe(chunk(0, 100_000, 140_000))
    assert all(w.start_ms + 100_000 >= 120_000 for u in partial.utterances for w in u.words)


def test_fake_scripted_failures_and_calls():
    t = FakeTranscriber(failures={1: [TranscriberTransientError("429", 429),
                                      TranscriberTransientError("429", 429)]})
    t.transcribe(chunk(0, 0, 10_000))
    for _ in range(2):
        with pytest.raises(TranscriberTransientError):
            t.transcribe(chunk(1, 10_000, 20_000))
    assert t.transcribe(chunk(1, 10_000, 20_000)).utterances
    assert [c.index for c in t.calls] == [0, 1, 1, 1]


def test_fake_language_and_invalid_key():
    assert FakeTranscriber().transcribe(chunk(0, 0, 6000, language="en")).language == "en"
    with pytest.raises(TranscriberAuthError):
        FakeTranscriber(api_key="invalid-123").transcribe(chunk(0, 0, 6000))
