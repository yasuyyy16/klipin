"""Adapter Deepgram pre-recorded (INT-04), sesuai dokumentasi resmi yang dicek 2026-11-21.

`POST /v1/listen` dengan body audio mentah, header `Authorization: Token {key}`.
Parameter: `model=nova-3`, `diarize_model=latest` (pengganti `diarize` yang deprecated),
`punctuate`, `smart_format`, `utterances`; `language={kode}` bila bahasa sudah diketahui,
selain itu `detect_language=true`. Waktu di respons dalam detik (float) relatif awal audio.
Error: 401/403 → API key; 400 → audio ditolak; 402 → kredit habis; 408/422/429/5xx/timeout →
boleh dicoba ulang (retry di handler `transcribe`).
"""

from collections.abc import Callable
from typing import Any

import httpx

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

BASE_URL = "https://api.deepgram.com/v1"
MODEL = "nova-3"  # 07-integrasi.md INT-04
TIMEOUT_S = 120.0  # per potongan (INT-04)
CONNECTION_TIMEOUT_S = 10.0  # tes koneksi (06-api.md §4)
TRANSIENT_STATUS = {408, 422, 429}
MSG_NO_CREDIT = "Kredit Deepgram habis. Isi ulang di konsol Deepgram lalu coba lagi."


def _detail(resp: httpx.Response) -> str:
    """Ringkasan error dari body Deepgram (format lama `err_code`/`err_msg` atau baru)."""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    code = body.get("err_code") or body.get("category") or body.get("error_code") or ""
    msg = body.get("err_msg") or body.get("message") or ""
    return f"HTTP {resp.status_code} {code}: {msg}".strip(": ")


def raise_for_status(resp: httpx.Response) -> None:
    status = resp.status_code
    if status < 400:
        return
    detail = _detail(resp)
    if status in (401, 403):
        raise TranscriberAuthError(detail)
    if status == 400:
        raise TranscriberBadAudioError(detail)
    if status == 402:
        raise TranscriberError(MSG_NO_CREDIT)
    if status in TRANSIENT_STATUS or status >= 500:
        raise TranscriberTransientError(detail, status)
    raise TranscriberError(f"Deepgram menolak permintaan ({detail}).")


def _ms(seconds: Any) -> int:
    return max(0, round(float(seconds) * 1000))


def _speaker(value: Any) -> str | None:
    return None if value is None else str(value)


def _word(w: dict[str, Any]) -> Word:
    confidence = w.get("confidence")
    return Word(start_ms=_ms(w["start"]), end_ms=_ms(w["end"]),
                word=w.get("punctuated_word") or w["word"],
                confidence=None if confidence is None else float(confidence),
                speaker=_speaker(w.get("speaker")))


def _language(code: Any) -> str | None:
    return code.split("-")[0].lower() if isinstance(code, str) and code else None


def parse_response(body: dict[str, Any], requested_language: str | None) -> TranscriptionResult:
    results = body.get("results") or {}
    channels = results.get("channels") or [{}]
    channel = channels[0]
    language = _language(channel.get("detected_language")) or requested_language
    utterances = []
    for u in results.get("utterances") or []:
        if u.get("channel", 0) != 0:
            continue
        words = [_word(w) for w in u.get("words") or [] if w.get("word")]
        if words:
            utterances.append(Utterance(start_ms=_ms(u["start"]), end_ms=_ms(u["end"]),
                                        text=u.get("transcript") or " ".join(w.word for w in words),
                                        speaker=_speaker(u.get("speaker")), words=words))
    if not utterances:  # tanpa `utterances`: kelompokkan kata berurutan per pembicara
        words = [_word(w) for w in (channel.get("alternatives") or [{}])[0].get("words") or []
                 if w.get("word")]
        group: list[Word] = []
        for w in words:
            if group and w.speaker != group[-1].speaker:
                utterances.append(_group(group))
                group = []
            group.append(w)
        if group:
            utterances.append(_group(group))
    return TranscriptionResult(language=language, utterances=utterances)


def _group(words: list[Word]) -> Utterance:
    return Utterance(start_ms=words[0].start_ms, end_ms=words[-1].end_ms,
                     text=" ".join(w.word for w in words), speaker=words[0].speaker,
                     words=list(words))


class DeepgramTranscriber(Transcriber):
    name = "deepgram"

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client()

    def transcribe(self, chunk: AudioChunk, *,
                   should_cancel: Callable[[], bool] | None = None) -> TranscriptionResult:
        params = {"model": MODEL, "diarize_model": "latest", "punctuate": "true",
                  "smart_format": "true", "utterances": "true"}
        if chunk.language:
            params["language"] = chunk.language
        else:
            params["detect_language"] = "true"
        try:
            resp = self._client.post(
                f"{BASE_URL}/listen", params=params, content=chunk.path.read_bytes(),
                headers={"Authorization": f"Token {self._key}", "Content-Type": "audio/flac"},
                timeout=TIMEOUT_S)
        except httpx.TimeoutException as e:
            raise TranscriberTransientError(f"timeout: {type(e).__name__}") from e
        except httpx.TransportError as e:
            raise TranscriberTransientError(f"jaringan: {type(e).__name__}") from e
        raise_for_status(resp)
        try:
            return parse_response(resp.json(), chunk.language)
        except (ValueError, KeyError, TypeError) as e:
            raise TranscriberError("Respons Deepgram tidak dikenali.") from e


def test_key(api_key: str, *, client: httpx.Client | None = None) -> None:
    """Tes koneksi: `GET /v1/projects`. Gagal → TranscriberError (pesan untuk Pengguna)."""
    try:
        resp = (client or httpx.Client()).get(
            f"{BASE_URL}/projects", headers={"Authorization": f"Token {api_key}"},
            timeout=CONNECTION_TIMEOUT_S)
    except httpx.HTTPError as e:
        raise TranscriberTransientError(f"{type(e).__name__}") from e
    raise_for_status(resp)
