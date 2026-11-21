from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from klipin.api.errors import user_error


class SubtitleOverrides(BaseModel):
    """05-database.md §6.3; kunci `words` = id Kata Transkrip, "" = kata disembunyikan."""

    model_config = ConfigDict(extra="forbid")

    words: dict[str, str] = Field(default_factory=dict)
    line_breaks_after_word_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids(self) -> "SubtitleOverrides":
        if not all(k.isdigit() for k in self.words):
            raise user_error("Kunci `words` harus id Kata Transkrip.")
        if any(len(v) > 100 for v in self.words.values()):
            raise user_error("Teks pengganti kata maksimal 100 karakter.")
        return self


class TranslatedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(max_length=300)


class ClipPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, gt=0)
    layout_preset_id: int | None = Field(None, ge=1)
    subtitle_style_id: int | None = Field(None, ge=1)
    subtitle_language: Literal["source", "id"] | None = None
    title: str | None = Field(None, max_length=100)
    subtitle_overrides: SubtitleOverrides | None = None
    translated_lines: list[TranslatedLine] | None = None


NOT_NULLABLE = ("start_ms", "end_ms", "layout_preset_id", "subtitle_style_id", "subtitle_language")


class ClipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class SnapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge: Literal["start", "end"]
    position_ms: int = Field(ge=0)
