"""T-029: tes kontrak adapter AssemblyAI (unggah → transkrip → polling) dengan respx.

Fixture `tests/fixtures/providers/assemblyai_*.json` dibuat dari format di dokumentasi resmi
AssemblyAI (dicek 2026-11-21), bukan dari panggilan API berbayar.
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
    TranscriberTransientError,
    assemblyai,
)
from klipin.providers.transcriber.base import MSG_API_KEY
from klipin.worker.process import JobCancelled

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
BASE = "https://api.assemblyai.com/v2"
TID = "9b3e5f70-0000-4000-8000-0000000000c1"
KEY = "aai-kunci-uji-123"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"assemblyai_{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "chunk_0000000000.flac"
    path.write_bytes(b"fLaC\x00audio-uji")
    return path


@pytest.fixture
def api_mock():
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BASE}/upload").mock(return_value=httpx.Response(200, json=fixture("upload")))
        mock.post(f"{BASE}/transcript").mock(
            return_value=httpx.Response(200, json=fixture("queued")))
        mock.delete(f"{BASE}/transcript/{TID}").mock(
            return_value=httpx.Response(200, json={"id": TID, "status": "completed"}))
        yield mock


def transcriber():
    return assemblyai.AssemblyAITranscriber(KEY, client=httpx.Client(), sleep=lambda s: None)


def poll_with(api_mock, *responses):
    return api_mock.get(f"{BASE}/transcript/{TID}").mock(side_effect=list(responses))


def test_success_flow_upload_submit_poll_delete(audio, api_mock):
    poll = poll_with(api_mock, httpx.Response(200, json=fixture("queued")),
                     httpx.Response(200, json={**fixture("queued"), "status": "processing"}),
                     httpx.Response(200, json=fixture("completed")))
    result = transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))

    upload = api_mock.routes[0].calls.last.request
    assert upload.headers["Authorization"] == KEY  # tanpa "Bearer"
    assert upload.headers["Content-Type"] == "application/octet-stream"
    assert upload.content == audio.read_bytes()
    submit = json.loads(api_mock.routes[1].calls.last.request.content)
    assert submit == {"audio_url": fixture("upload")["upload_url"],
                      "speech_models": ["universal-2"], "speaker_labels": True,
                      "punctuate": True, "format_text": True, "language_detection": True}
    assert poll.call_count == 3
    assert api_mock.routes[2].call_count == 1  # transkrip & unggahan dihapus

    assert result.language == "id"
    assert [(u.start_ms, u.end_ms, u.speaker, u.text) for u in result.utterances] == [
        (400, 1360, "A", "Halo semuanya."), (6080, 7440, "B", "Gila, kaget banget!")]
    w = result.utterances[1].words[0]
    assert (w.start_ms, w.end_ms, w.word, w.confidence, w.speaker) == (6080, 6400, "Gila,", 0.62, "B")


def test_known_language_sent_as_language_code(audio, api_mock):
    poll_with(api_mock, httpx.Response(200, json=fixture("completed")))
    transcriber().transcribe(AudioChunk(audio, 1, 600_000, 1_202_000, language="id"))
    submit = json.loads(api_mock.routes[1].calls.last.request.content)
    assert submit["language_code"] == "id"
    assert "language_detection" not in submit  # tidak boleh digabung dengan language_code


def test_language_code_normalized_and_words_fallback(audio, api_mock):
    body = {**fixture("completed"), "language_code": "en_us", "utterances": None}
    poll_with(api_mock, httpx.Response(200, json=body))
    result = transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert result.language == "en"
    assert [(u.speaker, u.text) for u in result.utterances] == [
        ("A", "Halo semuanya."), ("B", "Gila, kaget banget!")]


def test_silent_audio_no_utterances(audio, api_mock):
    body = {**fixture("completed"), "text": "", "words": [], "utterances": []}
    poll_with(api_mock, httpx.Response(200, json=body))
    assert transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000)).utterances == []


def test_status_error_is_bad_audio_and_still_deleted(audio, api_mock):
    poll_with(api_mock, httpx.Response(200, json=fixture("error_status")))
    with pytest.raises(TranscriberBadAudioError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert "does not appear to contain audio" in e.value.detail
    assert api_mock.routes[2].call_count == 1


def test_401_on_upload_is_auth_error(audio, api_mock):
    api_mock.post(f"{BASE}/upload").mock(return_value=httpx.Response(401, json=fixture("401")))
    with pytest.raises(TranscriberAuthError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert str(e.value) == MSG_API_KEY
    assert "API token missing/invalid" in e.value.detail and KEY not in e.value.detail


def test_429_on_submit_is_transient(audio, api_mock):
    api_mock.post(f"{BASE}/transcript").mock(return_value=httpx.Response(429, json=fixture("429")))
    with pytest.raises(TranscriberTransientError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert e.value.status == 429


def test_429_while_polling_waits_retry_after(audio, api_mock):
    waited = []
    t = assemblyai.AssemblyAITranscriber(KEY, client=httpx.Client(), sleep=waited.append)
    poll_with(api_mock, httpx.Response(429, json=fixture("429"), headers={"Retry-After": "2"}),
              httpx.Response(200, json=fixture("completed")))
    assert t.transcribe(AudioChunk(audio, 0, 0, 602_000)).utterances
    assert sum(waited) >= 1.5  # ditunggu sesuai Retry-After (dicicil per 0,5 dtk)


@pytest.mark.parametrize("status", [500, 503, 504])
def test_5xx_is_transient(audio, api_mock, status):
    poll_with(api_mock, httpx.Response(status, json=fixture("5xx")))
    with pytest.raises(TranscriberTransientError) as e:
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))
    assert e.value.status == status


def test_timeout_is_transient(audio, api_mock):
    api_mock.post(f"{BASE}/upload").mock(side_effect=httpx.WriteTimeout("lambat"))
    with pytest.raises(TranscriberTransientError):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))


def test_cancel_while_polling_deletes_transcript(audio, api_mock):
    poll = poll_with(api_mock, *[httpx.Response(200, json=fixture("queued"))] * 5)
    calls = iter([False, True])
    with pytest.raises(JobCancelled):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000),
                                 should_cancel=lambda: next(calls, True))
    assert poll.call_count == 1
    assert api_mock.routes[2].call_count == 1


def test_stuck_transcript_times_out(audio, api_mock, monkeypatch):
    monkeypatch.setattr(assemblyai, "MAX_WAIT_S", -1)
    poll_with(api_mock, httpx.Response(200, json=fixture("queued")))
    with pytest.raises(TranscriberTransientError, match="sibuk"):
        transcriber().transcribe(AudioChunk(audio, 0, 0, 602_000))


@respx.mock
def test_key_check_endpoint():
    route = respx.get(f"{BASE}/transcript").mock(
        return_value=httpx.Response(200, json=fixture("list")))
    assemblyai.test_key(KEY, client=httpx.Client())
    req = route.calls.last.request
    assert req.headers["Authorization"] == KEY and req.url.params["limit"] == "1"
    respx.get(f"{BASE}/transcript").mock(return_value=httpx.Response(401, json=fixture("401")))
    with pytest.raises(TranscriberAuthError):
        assemblyai.test_key("salah", client=httpx.Client())
