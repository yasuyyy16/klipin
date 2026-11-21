"""Adapter AssemblyAI (INT-04 alternatif), sesuai dokumentasi resmi yang dicek 2026-11-21.

Alur asinkron per potongan:
1. `POST /v2/upload` (body biner) → `upload_url`
2. `POST /v2/transcript` {audio_url, speech_models: ["universal-2"], speaker_labels,
   punctuate, format_text, language_code | language_detection}
3. `GET /v2/transcript/{id}` tiap 3 detik sampai `completed` / `error` (cek batal tiap putaran)
4. `DELETE /v2/transcript/{id}` (best effort): transkrip & file unggahan dihapus dari AssemblyAI.

Header `Authorization: {key}` (tanpa "Bearer"). Waktu kata/utterance dalam milidetik,
pembicara "A", "B", …; bahasa mis. "en_us". Error body `{"error": "..."}`.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx
import structlog

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
from klipin.worker.process import JobCancelled

log = structlog.get_logger(__name__)

BASE_URL = "https://api.assemblyai.com/v2"
SPEECH_MODELS = ["universal-2"]  # 07-integrasi.md INT-04; mendukung `id`
REQUEST_TIMEOUT_S = 120.0
CONNECTION_TIMEOUT_S = 10.0
POLL_S = 3.0  # contoh resmi memakai 3 detik
MAX_WAIT_S = 1800.0  # potongan 10 menit; lebih dari ini dianggap macet (boleh dicoba ulang)
CANCEL_CHECK_S = 0.5


def _detail(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error") or ""
    except (ValueError, AttributeError):
        msg = resp.text[:200]
    return f"HTTP {resp.status_code}: {msg}".strip(": ")


def raise_for_status(resp: httpx.Response) -> None:
    status = resp.status_code
    if status < 400:
        return
    detail = _detail(resp)
    if status in (401, 403):  # 403 juga untuk batas 20.000 request/5 menit; detail di log
        raise TranscriberAuthError(detail)
    if status in (400, 422):
        raise TranscriberBadAudioError(detail)
    if status in (408, 429) or status >= 500:
        raise TranscriberTransientError(detail, status)
    raise TranscriberError(f"AssemblyAI menolak permintaan ({detail}).")


def _speaker(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _word(w: dict[str, Any]) -> Word:
    confidence = w.get("confidence")
    return Word(start_ms=max(0, int(w["start"])), end_ms=max(0, int(w["end"])), word=w["text"],
                confidence=None if confidence is None else float(confidence),
                speaker=_speaker(w.get("speaker")))


def _language(code: Any) -> str | None:
    return code.replace("-", "_").split("_")[0].lower() if isinstance(code, str) and code else None


def parse_transcript(body: dict[str, Any], requested_language: str | None) -> TranscriptionResult:
    utterances = []
    for u in body.get("utterances") or []:
        words = [_word(w) for w in u.get("words") or [] if w.get("text")]
        if words:
            utterances.append(Utterance(start_ms=int(u["start"]), end_ms=int(u["end"]),
                                        text=u.get("text") or " ".join(w.word for w in words),
                                        speaker=_speaker(u.get("speaker")), words=words))
    if not utterances:  # tanpa speaker_labels: kelompokkan kata berurutan per pembicara
        group: list[Word] = []
        for w in (_word(x) for x in body.get("words") or [] if x.get("text")):
            if group and w.speaker != group[-1].speaker:
                utterances.append(_group(group))
                group = []
            group.append(w)
        if group:
            utterances.append(_group(group))
    return TranscriptionResult(language=_language(body.get("language_code")) or requested_language,
                               utterances=utterances)


def _group(words: list[Word]) -> Utterance:
    return Utterance(start_ms=words[0].start_ms, end_ms=words[-1].end_ms,
                     text=" ".join(w.word for w in words), speaker=words[0].speaker,
                     words=list(words))


class AssemblyAITranscriber(Transcriber):
    name = "assemblyai"

    def __init__(self, api_key: str, *, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._key = api_key
        self._client = client or httpx.Client()
        self._sleep = sleep

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": self._key, **kwargs.pop("headers", {})}
        try:
            return self._client.request(method, url, headers=headers,
                                        timeout=kwargs.pop("timeout", REQUEST_TIMEOUT_S), **kwargs)
        except httpx.TimeoutException as e:
            raise TranscriberTransientError(f"timeout: {type(e).__name__}") from e
        except httpx.TransportError as e:
            raise TranscriberTransientError(f"jaringan: {type(e).__name__}") from e

    def _wait(self, seconds: float, should_cancel: Callable[[], bool] | None) -> None:
        end = time.monotonic() + seconds
        while True:
            if should_cancel and should_cancel():
                raise JobCancelled
            left = end - time.monotonic()
            if left <= 0:
                return
            self._sleep(min(CANCEL_CHECK_S, left))

    def _delete(self, transcript_id: str) -> None:
        try:
            resp = self._request("DELETE", f"{BASE_URL}/transcript/{transcript_id}")
            if resp.status_code >= 400:
                log.warning("hapus transkrip AssemblyAI gagal", detail=_detail(resp))
        except TranscriberError as e:
            log.warning("hapus transkrip AssemblyAI gagal", detail=getattr(e, "detail", ""))

    def transcribe(self, chunk: AudioChunk, *,
                   should_cancel: Callable[[], bool] | None = None) -> TranscriptionResult:
        upload = self._request("POST", f"{BASE_URL}/upload", content=chunk.path.read_bytes(),
                               headers={"Content-Type": "application/octet-stream"})
        raise_for_status(upload)
        body: dict[str, Any] = {"audio_url": upload.json()["upload_url"],
                                "speech_models": SPEECH_MODELS, "speaker_labels": True,
                                "punctuate": True, "format_text": True}
        if chunk.language:
            body["language_code"] = chunk.language
        else:
            body["language_detection"] = True
        created = self._request("POST", f"{BASE_URL}/transcript", json=body)
        raise_for_status(created)
        transcript_id = created.json()["id"]
        try:
            return self._poll(transcript_id, chunk, should_cancel)
        finally:
            self._delete(transcript_id)

    def _poll(self, transcript_id: str, chunk: AudioChunk,
              should_cancel: Callable[[], bool] | None) -> TranscriptionResult:
        deadline = time.monotonic() + MAX_WAIT_S
        while True:
            resp = self._request("GET", f"{BASE_URL}/transcript/{transcript_id}")
            if resp.status_code == 429:  # batas GET per transkrip: tunggu Retry-After
                try:
                    delay = float(resp.headers.get("Retry-After", POLL_S))
                except ValueError:
                    delay = POLL_S
                self._wait(delay, should_cancel)
                continue
            raise_for_status(resp)
            data = resp.json()
            status = data.get("status")
            if status == "completed":
                try:
                    return parse_transcript(data, chunk.language)
                except (KeyError, TypeError, ValueError) as e:
                    raise TranscriberError("Respons AssemblyAI tidak dikenali.") from e
            if status == "error":
                raise TranscriberBadAudioError(f"status error: {data.get('error') or ''}")
            if time.monotonic() > deadline:
                raise TranscriberTransientError(f"transkrip {status} > {MAX_WAIT_S:.0f} dtk")
            self._wait(POLL_S, should_cancel)


def test_key(api_key: str, *, client: httpx.Client | None = None) -> None:
    """Tes koneksi: `GET /v2/transcript?limit=1`. Gagal → TranscriberError."""
    try:
        resp = (client or httpx.Client()).get(
            f"{BASE_URL}/transcript", params={"limit": 1}, headers={"Authorization": api_key},
            timeout=CONNECTION_TIMEOUT_S)
    except httpx.HTTPError as e:
        raise TranscriberTransientError(type(e).__name__) from e
    raise_for_status(resp)
