"""T-011: proteksi API lokal (ADR-009) + format error 06-api.md §1. TC-070, TC-071, TC-072."""

import socket

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from klipin.__main__ import bind_sockets
from klipin.api.app import create_app
from klipin.api.errors import ApiError

TOKEN = "tok-uji-123"
PORT = 8765
HOST = {"Host": f"127.0.0.1:{PORT}"}
AUTH = {**HOST, "X-Klipin-Token": TOKEN}


class Body(BaseModel):
    end_ms: int


@pytest.fixture
def client(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head><title>Klipin</title></head><body></body></html>")
    (dist / "app.js").write_text("console.log(1)")
    router = APIRouter(prefix="/api/v1")

    @router.post("/streams")
    def streams() -> dict:
        return {"ok": True}

    @router.get("/events")
    def events() -> dict:
        return {"ok": True}

    @router.get("/media/clips/{clip_id}/video")
    def media(clip_id: int) -> dict:
        return {"ok": clip_id}

    @router.get("/settings")
    def settings() -> dict:
        return {"ok": True}

    @router.post("/validate")
    def validate(body: Body) -> dict:
        return {"ok": body.end_ms}

    @router.get("/conflict")
    def conflict() -> dict:
        raise ApiError(409, "INVALID_STATE", "Setujui klip dulu sebelum render.")

    @router.get("/boom")
    def boom() -> dict:
        raise RuntimeError("detail rahasia internal")

    app = create_app(token=TOKEN, dist_dir=dist, port=PORT, routers=[router])
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}", raise_server_exceptions=False)


def assert_forbidden(resp):
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_ORIGIN"
    assert not any(h.lower().startswith("access-control-") for h in resp.headers)


def test_tc070_post_without_token_forbidden(client):
    assert_forbidden(client.post("/api/v1/streams", headers={
        **HOST, "Origin": "https://evil.example"}))


def test_tc070_preflight_gets_no_cors(client):
    assert_forbidden(client.options("/api/v1/streams", headers={
        **HOST, "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}))


def test_wrong_token_forbidden(client):
    assert_forbidden(client.post("/api/v1/streams", headers={**HOST, "X-Klipin-Token": "salah"}))


def test_valid_token_passes_without_cors_headers(client):
    resp = client.post("/api/v1/streams", headers=AUTH)
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize("host", ["evil.example:8765", "127.0.0.1:9999", "192.168.1.5:8765", ""])
def test_tc071_foreign_host_forbidden_everywhere(client, host):
    headers = {"Host": host, "X-Klipin-Token": TOKEN}
    assert_forbidden(client.post("/api/v1/streams", headers=headers))
    assert_forbidden(client.get("/", headers=headers))  # index.html berisi token


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "LOCALHOST:8765"])
def test_loopback_hosts_allowed(client, host):
    assert client.post("/api/v1/streams", headers={"Host": host, "X-Klipin-Token": TOKEN}
                       ).status_code == 200


@pytest.mark.parametrize(("path", "ok"), [
    ("/api/v1/events", True),
    ("/api/v1/media/clips/3/video", True),
    ("/api/v1/settings", False),  # ?t= hanya untuk SSE & media
])
def test_query_token_only_for_sse_and_media(client, path, ok):
    resp = client.get(f"{path}?t={TOKEN}", headers=HOST)
    if ok:
        assert resp.status_code == 200
    else:
        assert_forbidden(resp)


def test_index_injects_token_and_is_not_cached(client):
    resp = client.get("/", headers=HOST)
    assert resp.status_code == 200
    assert f'<meta name="klipin-token" content="{TOKEN}"></head>' in resp.text
    assert resp.headers["cache-control"] == "no-store"


def test_static_assets_need_no_token(client):
    assert client.get("/app.js", headers=HOST).status_code == 200


def test_error_format_validation(client):
    resp = client.post("/api/v1/validate", headers=AUTH, json={"end_ms": "bukan angka"})
    assert resp.status_code == 400
    assert resp.json() == {"error": {"code": "VALIDATION_ERROR", "message": "Input tidak valid.",
                                     "fields": {"end_ms": "Nilai tidak valid."}}}


def test_error_format_api_error(client):
    resp = client.get("/api/v1/conflict", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json() == {"error": {"code": "INVALID_STATE",
                                     "message": "Setujui klip dulu sebelum render."}}


def test_error_format_not_found(client):
    resp = client.get("/api/v1/tidak-ada", headers=AUTH)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_unexpected_error_hides_details(client):
    resp = client.get("/api/v1/boom", headers=AUTH)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "rahasia" not in resp.text


def test_tc072_binds_loopback_only():
    socks = bind_sockets(["127.0.0.1", "::1"], 0)
    try:
        addrs = {s.getsockname()[0] for s in socks}
        assert addrs <= {"127.0.0.1", "::1"}
        assert "127.0.0.1" in addrs
        for s in socks:
            if s.family == socket.AF_INET6:
                assert s.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 1
    finally:
        for s in socks:
            s.close()
