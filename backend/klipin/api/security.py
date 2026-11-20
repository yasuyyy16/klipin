"""Proteksi API lokal (ADR-009, BR-012): header Host loopback + token sesi."""

import secrets
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

from klipin.api.errors import STATUS_MESSAGES, error_response

API_PREFIX = "/api/v1"
# <video src> dan EventSource tidak bisa memasang header, jadi hanya di sini ?t= diterima.
QUERY_TOKEN_PATHS = (f"{API_PREFIX}/events", f"{API_PREFIX}/media/")


def allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


class LocalOnlyMiddleware:
    """Tolak Host selain loopback (DNS rebinding) di semua path, termasuk index.html yang
    memuat token; untuk /api/v1/* wajib token sesi. Tidak ada header CORS sama sekali."""

    def __init__(self, app: ASGIApp, token: str, port: int) -> None:
        self.app, self.token, self.hosts = app, token, allowed_hosts(port)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode("latin-1").lower()
        path = scope["path"]
        if host not in self.hosts or (
            (path == API_PREFIX or path.startswith(API_PREFIX + "/"))
            and not self._token_ok(path, headers, scope["query_string"])
        ):
            response = error_response(403, "FORBIDDEN_ORIGIN", STATUS_MESSAGES[403])
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _token_ok(self, path: str, headers: dict[bytes, bytes], query: bytes) -> bool:
        supplied = headers.get(b"x-klipin-token", b"").decode("latin-1")
        if not supplied and (path == QUERY_TOKEN_PATHS[0] or path.startswith(QUERY_TOKEN_PATHS[1])):
            supplied = parse_qs(query.decode("latin-1")).get("t", [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, self.token)
