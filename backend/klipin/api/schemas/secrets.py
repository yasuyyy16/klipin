from pydantic import BaseModel


class SecretPutRequest(BaseModel):
    value: str


class SecretResponse(BaseModel):
    name: str
    set: bool
    masked: str | None


class SecretTestResponse(BaseModel):
    ok: bool
    provider: str
    latency_ms: int | None = None
    error: str | None = None
