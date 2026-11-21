from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from klipin.api.errors import user_error


class RegionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["cam", "content", "face_a", "face_b"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0.05, le=1)
    h: float = Field(ge=0.05, le=1)

    @model_validator(mode="after")
    def _inside(self) -> "RegionIn":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:  # CHECK cam_regions
            raise user_error("Region keluar dari frame.")
        return self


class ClipRegionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[RegionIn] = Field(max_length=2)
    save_as_channel_default: bool = False
    apply_to_stream_clips: bool = False

    @model_validator(mode="after")
    def _unique_roles(self) -> "ClipRegionsRequest":
        roles = [r.role for r in self.regions]
        if len(roles) != len(set(roles)):
            raise user_error("Setiap role region hanya boleh sekali.")
        return self


class ChannelCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StreamChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: int = Field(ge=1)
