"""PATCH /settings: subset kunci 05-database.md §6.2, validasi 02-requirements.md §3."""

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from klipin.api.errors import user_error

Platform = Literal["youtube", "tiktok", "instagram", "facebook"]
Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ScoreWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio: float = Field(ge=0, le=1)
    chat: float = Field(ge=0, le=1)
    llm: float = Field(ge=0, le=1)


def _weights_total(w: ScoreWeights) -> ScoreWeights:
    if abs(w.audio + w.chat + w.llm - 1) > 0.001:  # BR-001, toleransi 0,001
        raise user_error("Total bobot harus 100%.")
    return w


class LlmModels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    judge_highlight: str | None
    translate_lines: str | None
    write_captions: str | None


class SettingsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_weights: Annotated[ScoreWeights, AfterValidator(_weights_total)] | None = None
    score_min_threshold: int | None = Field(None, ge=0, le=100)
    chat_delay_ms: int | None = None
    chat_reaction_words: list[Word] | None = Field(None, max_length=200)
    live_segment_seconds: int | None = Field(None, ge=1)
    live_block_minutes: int | None = Field(None, ge=1)
    live_last_n_default_s: int | None = None
    max_heavy_jobs: int | None = Field(None, ge=1)
    confirm_usage_over_min: int | None = Field(None, ge=0)
    max_audio_minutes_per_job: int | None = Field(None, ge=1)
    transcriber_provider: Literal["deepgram", "assemblyai"] | None = None
    llm_provider: Literal["anthropic"] | None = None
    llm_models: LlmModels | None = None
    kick_live_chat_enabled: bool | None = None
    default_subtitle_style: str | None = None
    output_dir: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    download_max_height: int | None = Field(None, ge=1)
    upload_default_mode: Literal["manual", "auto"] | None = None
    caption_templates: dict[Platform, Annotated[str, StringConstraints(max_length=2000)]] | None = None
    upload_platforms_enabled: list[Platform] | None = None
    manual_upload_urls: dict[Platform, Annotated[str, StringConstraints(
        pattern=r"^https://\S+$")]] | None = None

    @field_validator("chat_delay_ms")
    @classmethod
    def _chat_delay(cls, v: int | None) -> int | None:
        if v is not None and not 0 <= v <= 30_000:
            raise user_error("Jeda chat harus 0–30 detik.")
        return v

    @field_validator("live_last_n_default_s")
    @classmethod
    def _last_n(cls, v: int | None) -> int | None:
        if v is not None and not 15 <= v <= 90:
            raise user_error("Pilih durasi antara 15 dan 90 detik.")
        return v
