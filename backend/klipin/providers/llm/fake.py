"""`FakeJudge` (KLIPIN_PROVIDERS=fake): penilaian deterministik dari angka Sinyal, tanpa jaringan.

Skor = 100 × rata-rata Sinyal Audio dan Chat (Chat tidak ada → Audio). Kategori `hype` bila
skor ≥ 70, `lucu` bila transkrip memuat "wkwk"/"haha", selain itu `lainnya`. Rentang saran =
seluruh jendela. Perilaku bisa diskenariokan per `key` jendela:
`invalid_times` (berapa kali respons tidak valid) atau `fail` (gagal permanen).
"""

from collections.abc import Callable

from klipin.providers.llm.base import HighlightJudge, Judgement, JudgeResult, WindowInput

MAX_VALIDATION_ATTEMPTS = 2  # 1 percobaan + 1 coba ulang (FR-011)


class FakeJudge(HighlightJudge):
    name = "fake"

    def __init__(self, *, invalid_times: dict[int, int] | None = None,
                 fail: set[int] | None = None) -> None:
        self.invalid_times = dict(invalid_times or {})
        self.fail = set(fail or ())
        self.calls: list[int] = []  # satu entri per permintaan (termasuk coba ulang)

    def _respond(self, w: WindowInput) -> Judgement | None:
        self.calls.append(w.key)
        if self.invalid_times.get(w.key, 0) > 0:
            self.invalid_times[w.key] -= 1
            return None
        signals = [w.audio_signal] + ([w.chat_signal] if w.chat_signal is not None else [])
        score = round(100 * sum(signals) / len(signals))
        text = " ".join(w.transcript).lower()
        category = "hype" if score >= 70 else ("lucu" if "wkwk" in text or "haha" in text
                                               else "lainnya")
        length_s = (w.end_ms - w.start_ms) / 1000
        return Judgement(score=score, category=category,
                         reason="Penilaian uji dari angka sinyal.",
                         suggested_start_s=0.0, suggested_end_s=length_s,
                         title=f"Momen detik {w.start_ms // 1000}")

    def judge(self, window: WindowInput, *,
              should_cancel: Callable[[], bool] | None = None) -> JudgeResult:
        if window.key in self.fail:
            self.calls.append(window.key)
            return JudgeResult("failed", detail="gagal palsu", attempts=1)
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            judgement = self._respond(window)
            if judgement is not None:
                return JudgeResult("done", judgement, attempts=attempt)
        return JudgeResult("invalid", detail="respons palsu tidak valid",
                           attempts=MAX_VALIDATION_ATTEMPTS)
