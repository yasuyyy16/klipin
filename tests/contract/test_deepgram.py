"""T-028: tes kontrak adapter Deepgram (INT-04) dengan respons rekaman (respx, tanpa jaringan).

Fixture `tests/fixtures/providers/deepgram_*.json` dibuat dari format di dokumentasi resmi
Deepgram (dicek 2026-11-21), bukan dari panggilan API berbayar.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from klipin.providers.transcriber import (
    AudioChunk,
    TranscriberAuthError,
    TranscriberBadAudioError,
    TranscriberError,
    TranscriberTransientError,
    deepgram,
)
from klipin.providers.transcriber.base import MSG_API_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
LISTEN = "https://api.deepgram.com/v1/listen"
KEY = "dg-kunci-uji-123"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"deepgram_{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "chunk_0000000000.flac"
    path.write_bytes(b"fLaC\x00audio-uji")
    return path


def transcriber():
    return deepgram.DeepgramTranscriber(KEY, client=httpx.Client())


@respx.mock
def test_success_detects_language_and_normalizes(audio):
    route = respx.post(LISTEN).mock(return_value=httpx.Response(200, json=fixture("success")))
    result = transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))

    req = route.calls.last.request
    assert req.headers["Authorization"] == f"Token {KEY}"
    assert req.headers["Content-Type"] == "audio/flac"
    assert req.content == audio.read_bytes()
    params = dict(req.url.params)
    assert params == {"model": "nova-3", "diarize_model": "latest", "punctuate": "true",
                      "smart_format": "true", "utterances": "true", "detect_language": "true"}

    assert result.language == "id"
    assert [(u.start_ms, u.end_ms, u.speaker, u.text) for u in result.utterances] == [
        (400, 1360, "0", "Halo semuanya."), (6080, 7440, "1", "Gila, kaget banget!")]
    w = result.utterances[1].words[0]
    assert (w.start_ms, w.end_ms, w.word, w.confidence, w.speaker) == (6080, 6400, "Gila,", 0.62, "1")


@respx.mock
def test_known_language_sent_explicitly(audio):
    route = respx.post(LISTEN).mock(return_value=httpx.Response(200, json=fixture("success")))
    transcriber().transcribe(AudioChunk(audio, 1, 600_000, 1_202_000, language="id"))
    params = dict(route.calls.last.request.url.params)
    assert params["language"] == "id"
    assert "detect_language" not in params


@respx.mock
def test_words_without_utterances_grouped_by_speaker(audio):
    body = fixture("success")
    del body["results"]["utterances"]
    respx.post(LISTEN).mock(return_value=httpx.Response(200, json=body))
    result = transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000, language="id"))
    assert [(u.speaker, u.text) for u in result.utterances] == [
        ("0", "Halo semuanya."), ("1", "Gila, kaget banget!")]


@respx.mock
def test_silent_audio_returns_no_utterances(audio):
    body = {"metadata": {}, "results": {"channels": [{"alternatives": [
        {"transcript": "", "confidence": 0.0, "words": []}]}], "utterances": []}}
    respx.post(LISTEN).mock(return_value=httpx.Response(200, json=body))
    result = transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert result.utterances == []
    assert result.language is None


@respx.mock
def test_401_is_auth_error_without_leaking_key(audio):
    respx.post(LISTEN).mock(return_value=httpx.Response(401, json=fixture("401")))
    with pytest.raises(TranscriberAuthError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert str(e.value) == MSG_API_KEY
    assert "INVALID_AUTH" in e.value.detail
    assert KEY not in e.value.detail


@respx.mock
def test_429_is_transient(audio):
    respx.post(LISTEN).mock(return_value=httpx.Response(429, json=fixture("429")))
    with pytest.raises(TranscriberTransientError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert e.value.status == 429
    assert "TOO_MANY_REQUESTS" in e.value.detail


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@respx.mock
def test_5xx_is_transient(audio, status):
    respx.post(LISTEN).mock(return_value=httpx.Response(status, json=fixture("5xx")))
    with pytest.raises(TranscriberTransientError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert e.value.status == status


@respx.mock
def test_5xx_non_json_body_is_transient(audio):
    respx.post(LISTEN).mock(return_value=httpx.Response(503, text="<html>bad gateway</html>"))
    with pytest.raises(TranscriberTransientError):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))


@respx.mock
def test_timeout_and_network_errors_are_transient(audio):
    respx.post(LISTEN).mock(side_effect=httpx.ReadTimeout("lambat"))
    with pytest.raises(TranscriberTransientError, match="sibuk"):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    respx.post(LISTEN).mock(side_effect=httpx.ConnectError("putus"))
    with pytest.raises(TranscriberTransientError):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))


@respx.mock
def test_400_bad_audio_and_402_no_credit(audio):
    respx.post(LISTEN).mock(return_value=httpx.Response(400, json=fixture("400")))
    with pytest.raises(TranscriberBadAudioError):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    respx.post(LISTEN).mock(return_value=httpx.Response(402, json={
        "err_code": "ASR_PAYMENT_REQUIRED", "err_msg": "Project does not have enough credits"}))
    with pytest.raises(TranscriberError, match="Kredit Deepgram habis"):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))


@respx.mock
def test_key_check_endpoint():
    route = respx.get("https://api.deepgram.com/v1/projects").mock(
        return_value=httpx.Response(200, json=fixture("projects")))
    deepgram.test_key(KEY, client=httpx.Client())
    assert route.calls.last.request.headers["Authorization"] == f"Token {KEY}"
    respx.get("https://api.deepgram.com/v1/projects").mock(
        return_value=httpx.Response(401, json=fixture("401")))
    with pytest.raises(TranscriberAuthError):
        deepgram.test_key("salah", client=httpx.Client())


@respx.mock
def test_secret_test_endpoint_uses_deepgram_in_real_mode(api, memory_keyring, monkeypatch):
    from klipin import secrets
    from klipin.config import get_config

    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    secrets.set_secret("transcriber_api_key", KEY)
    respx.get("https://api.deepgram.com/v1/projects").mock(
        return_value=httpx.Response(401, json=fixture("401")))
    body = api.post("/api/v1/secrets/transcriber_api_key/test").json()
    assert body["ok"] is False and body["provider"] == "deepgram"
    assert "INVALID_AUTH" in body["error"] and KEY not in body["error"]
    respx.get("https://api.deepgram.com/v1/projects").mock(
        return_value=httpx.Response(200, json=fixture("projects")))
    body = api.post("/api/v1/secrets/transcriber_api_key/test").json()
    assert body["ok"] is True and body["latency_ms"] >= 0
