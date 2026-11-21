"""Adapter Anthropic Claude untuk `judge_highlight` (INT-05, FR-011).

- SDK resmi `anthropic`, `messages.create` dengan `output_config.format` (JSON schema) lalu
  divalidasi Pydantic (`Judgement`). Respons tidak valid / terpotong `max_tokens` → coba ulang
  1×, lalu `invalid` (Sinyal LLM null, BR-002).
- Nama model dari Pengaturan `llm_models.judge_highlight` (tidak di-hardcode).
- 429/5xx/overloaded/jaringan → coba ulang 3× dengan backoff 2/4/8 detik + jitter (retry
  bawaan SDK dimatikan agar tidak berlapis). Penolakan (`stop_reason = refusal`) → `failed`.
- 401/403/404/400 → `JudgeUnavailable` (konfigurasi salah untuk seluruh Job).
- `max_tokens` 300 dan effort `low` sesuai kontrol biaya INT-05. Tidak mengirim nama penonton,
  API key, atau path file.
"""

import json
import random
import time
from collections.abc import Callable
from typing import Any

import anthropic
from pydantic import ValidationError

from klipin.providers.llm.base import (
    CATEGORIES,
    HighlightJudge,
    Judgement,
    JudgeResult,
    JudgeUnavailable,
    WindowInput,
)
from klipin.worker.process import JobCancelled

MAX_TOKENS = 300  # INT-05
EFFORT = "low"
TIMEOUT_S = 60.0
BACKOFF_S = (2.0, 4.0, 8.0)
JITTER_S = 0.5
MAX_VALIDATION_ATTEMPTS = 2
TRANSCRIPT_MAX_CHARS = 6000  # ±1.500 token (INT-05)

SYSTEM_PROMPT = """Kamu menilai potongan livestream untuk dijadikan klip vertikal pendek.
Nilai satu jendela transkrip. Balas hanya dengan JSON sesuai skema.

Aturan:
- score 0–100. Beri ≥ 70 hanya jika momen layak berdiri sendiri sebagai klip tanpa konteks.
- category salah satu: lucu, hype, kontroversial, informatif, emosional, lainnya.
- reason maksimal 20 kata, bahasa Indonesia, jelaskan kenapa momen ini menarik (atau tidak).
- suggested_start_s dan suggested_end_s dalam detik relatif awal jendela, berada di dalam
  jendela, durasi 15–90 detik, mulai dan berakhir di batas kalimat.
- title maksimal 60 karakter, tanpa clickbait yang menyesatkan.
- Angka Sinyal Audio/Chat (0–1) hanya petunjuk; dasarkan penilaian pada isi transkrip."""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "reason": {"type": "string"},
        "suggested_start_s": {"type": "number"},
        "suggested_end_s": {"type": "number"},
        "title": {"type": "string"},
    },
    "required": ["score", "category", "reason", "suggested_start_s", "suggested_end_s", "title"],
    "additionalProperties": False,
}

TRANSIENT = (anthropic.RateLimitError, anthropic.InternalServerError,
             anthropic.APIConnectionError)  # APITimeoutError turunan APIConnectionError
UNAVAILABLE = (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
               anthropic.NotFoundError, anthropic.BadRequestError)


def build_prompt(w: WindowInput) -> str:
    transcript = "\n".join(w.transcript) or "(tidak ada ucapan)"
    if len(transcript) > TRANSCRIPT_MAX_CHARS:
        transcript = transcript[:TRANSCRIPT_MAX_CHARS] + "\n[dipangkas]"
    chat = "tidak tersedia" if w.chat_signal is None else f"{w.chat_signal:.2f}"
    return (f"Durasi jendela: {(w.end_ms - w.start_ms) / 1000:.0f} detik\n"
            f"Bahasa: {w.language or 'tidak diketahui'}\n"
            f"Preset Layout: {w.layout_preset or '-'}\n"
            f"Sinyal Audio: {w.audio_signal:.2f}; Sinyal Chat: {chat}\n\n"
            f"Transkrip (detik relatif awal jendela, S1/S2 = pembicara):\n{transcript}")


def parse_judgement(message: Any) -> tuple[Judgement | None, str]:
    """(judgement, detail). `None` bila respons tidak bisa dipakai."""
    if message.stop_reason == "max_tokens":
        return None, "respons terpotong max_tokens"
    text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
    try:
        return Judgement.model_validate(json.loads(text)), ""
    except (ValueError, ValidationError) as e:
        return None, f"respons tidak valid: {str(e)[:200]}"


class AnthropicJudge(HighlightJudge):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, *, client: anthropic.Anthropic | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.model = model
        self._client = client or anthropic.Anthropic(api_key=api_key, max_retries=0,
                                                     timeout=TIMEOUT_S)
        self._sleep = sleep

    def _create(self, w: WindowInput, should_cancel: Callable[[], bool] | None) -> Any:
        for attempt in range(len(BACKOFF_S) + 1):
            if should_cancel and should_cancel():
                raise JobCancelled
            try:
                return self._client.messages.create(
                    model=self.model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": build_prompt(w)}],
                    output_config={"effort": EFFORT,
                                   "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}})
            except UNAVAILABLE as e:
                raise JudgeUnavailable(
                    "LLM menolak permintaan (API key, model, atau izin). Cek Pengaturan. "
                    "Skor memakai Sinyal Audio dan Chat saja.",
                    f"{type(e).__name__}: {getattr(e, 'message', e)}") from e
            except TRANSIENT:
                if attempt == len(BACKOFF_S):
                    raise
                self._sleep(BACKOFF_S[attempt] + random.uniform(0, JITTER_S))
        raise AssertionError("tidak tercapai")

    def judge(self, window: WindowInput, *,
              should_cancel: Callable[[], bool] | None = None) -> JudgeResult:
        detail = ""
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            try:
                message = self._create(window, should_cancel)
            except TRANSIENT as e:
                return JudgeResult("failed", detail=f"{type(e).__name__}", attempts=attempt)
            except anthropic.APIStatusError as e:
                return JudgeResult("failed", detail=f"HTTP {e.status_code}", attempts=attempt)
            if message.stop_reason == "refusal":
                return JudgeResult("failed", detail="refusal", attempts=attempt)
            judgement, detail = parse_judgement(message)
            if judgement is not None:
                return JudgeResult("done", judgement, attempts=attempt)
        return JudgeResult("invalid", detail=detail, attempts=MAX_VALIDATION_ATTEMPTS)


def test_key(api_key: str, *, client: anthropic.Anthropic | None = None) -> None:
    """Tes koneksi tanpa biaya token: `GET /v1/models` (daftar model)."""
    c = client or anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=10.0)
    c.models.list(limit=1)
