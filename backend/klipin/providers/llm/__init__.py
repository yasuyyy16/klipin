"""Pemilihan penilai highlight & penilaian paralel (ADR-003, INT-05).

Urutan: API key LLM wajib (tanpa key → `JudgeUnavailable`, skor parsial); `KLIPIN_PROVIDERS=fake`
→ `FakeJudge`; selain itu penyedia dari Pengaturan `llm_provider` (env hanya cadangan) dengan
model dari `llm_models.judge_highlight`.
"""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import Engine

from klipin import app_settings, secrets
from klipin.config import get_config
from klipin.providers.llm.base import (
    MSG_NO_KEY,
    MSG_NO_MODEL,
    HighlightJudge,
    Judgement,
    JudgeResult,
    JudgeUnavailable,
    WindowInput,
)
from klipin.providers.llm.fake import FakeJudge

__all__ = ["FakeJudge", "HighlightJudge", "JudgeResult", "JudgeUnavailable", "Judgement",
           "WindowInput", "get_judge", "judge_all"]

SECRET = "llm_api_key"
PARALLEL = 4  # INT-05


def get_judge(engine: Engine) -> HighlightJudge:
    key = secrets.get_secret(SECRET)
    if not key:
        raise JudgeUnavailable(MSG_NO_KEY)
    if get_config().klipin_providers == "fake":
        return FakeJudge()
    with engine.connect() as conn:
        provider = app_settings.value(conn, "llm_provider") or get_config().klipin_llm_provider
        models = app_settings.value(conn, "llm_models") or {}
    model = (models or {}).get("judge_highlight")
    if not model:
        raise JudgeUnavailable(MSG_NO_MODEL)
    if provider == "anthropic":
        from klipin.providers.llm.anthropic_judge import AnthropicJudge

        return AnthropicJudge(key, model)
    raise JudgeUnavailable(f"Penyedia LLM {provider} belum tersedia di versi ini.")


def judge_all(judge: HighlightJudge, windows: Sequence[WindowInput], *,
              should_cancel: Callable[[], bool] | None = None,
              on_result: Callable[[WindowInput, JudgeResult], None] | None = None,
              parallel: int = PARALLEL) -> dict[int, JudgeResult]:
    """Nilai semua jendela, maks. `parallel` permintaan sekaligus. `JudgeUnavailable` dan
    `JobCancelled` dari satu jendela diteruskan ke pemanggil (sisa antrean dibatalkan)."""
    results: dict[int, JudgeResult] = {}
    with ThreadPoolExecutor(max_workers=parallel, thread_name_prefix="judge") as pool:
        futures = {pool.submit(judge.judge, w, should_cancel=should_cancel): w for w in windows}
        try:
            for future, window in futures.items():
                result = future.result()
                results[window.key] = result
                if on_result:
                    on_result(window, result)
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    return results
