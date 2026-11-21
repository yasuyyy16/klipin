"""Gabung Sinyal menjadi Skor Highlight (BR-001) dengan aturan Sinyal yang tidak tersedia (BR-002).

- Sinyal Chat tidak tersedia (stream tanpa chat) → `w_chat` dibagi ke `w_audio` dan `w_llm`
  secara proporsional terhadap bobot keduanya.
- Sinyal LLM null untuk satu jendela → skor memakai Sinyal yang tersedia saja (bobot sisanya
  dinormalkan ulang) dan diberi tanda "skor parsial".
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Weights:
    audio: float
    chat: float
    llm: float

    @classmethod
    def from_setting(cls, value: Mapping[str, float]) -> "Weights":
        return cls(float(value["audio"]), float(value["chat"]), float(value["llm"]))


def without_chat(w: Weights) -> Weights:
    """BR-002: bobot chat dibagi proporsional ke audio & LLM."""
    rest = w.audio + w.llm
    if rest <= 0:  # semua bobot di chat: bagi rata
        return Weights(w.chat / 2, 0.0, w.chat / 2)
    return Weights(w.audio + w.chat * w.audio / rest, 0.0, w.llm + w.chat * w.llm / rest)


@dataclass(frozen=True)
class Score:
    value: int  # 0–100
    partial: bool


def combine(audio: float, chat: float | None, llm: int | None, weights: Weights) -> Score:
    """Skor Highlight = 100 × (w_audio·Audio + w_chat·Chat + w_llm·LLM/100)."""
    w = weights if chat is not None else without_chat(weights)
    parts = [(w.audio, audio), (w.chat, chat or 0.0)]
    partial = llm is None
    if partial:
        total = w.audio + w.chat
        if total <= 0:
            return Score(0, True)
        parts = [(wt / total, s) for wt, s in parts]
    else:
        parts.append((w.llm, llm / 100))
    value = 100 * sum(wt * s for wt, s in parts)
    return Score(max(0, min(100, round(value))), partial)
