"""Format error standar 06-api.md §1: {"error": {"code", "message", "fields"?}}."""

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)

STATUS_CODES = {400: "VALIDATION_ERROR", 403: "FORBIDDEN_ORIGIN", 404: "NOT_FOUND",
                409: "INVALID_STATE", 502: "UPSTREAM_ERROR"}
STATUS_MESSAGES = {404: "Data tidak ditemukan.", 403: "Sesi tidak valid. Muat ulang halaman Klipin."}
INTERNAL_MESSAGE = "Terjadi kesalahan di Klipin. Detail ada di log."


class ApiError(Exception):
    """Error yang ditampilkan ke Pengguna; `message` dalam Bahasa Indonesia."""

    def __init__(self, status: int, code: str, message: str,
                 fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields


def error_response(status: int, code: str, message: str,
                   fields: dict[str, str] | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return JSONResponse({"error": body}, status_code=status)


def _field_message(err: dict) -> str:
    return "Wajib diisi." if err.get("type") == "missing" else "Nilai tidak valid."


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {}
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            fields[".".join(loc) or "body"] = _field_message(err)
        log.info("validasi gagal", errors=exc.errors())
        return error_response(400, "VALIDATION_ERROR", "Input tidak valid.", fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        code = STATUS_CODES.get(status, "INTERNAL_ERROR" if status >= 500 else "VALIDATION_ERROR")
        message = STATUS_MESSAGES.get(status, INTERNAL_MESSAGE if status >= 500
                                      else "Permintaan tidak valid.")
        return error_response(status, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(req: Request, exc: Exception) -> JSONResponse:
        log.exception("error tak terduga", path=req.url.path)
        return error_response(500, "INTERNAL_ERROR", INTERNAL_MESSAGE)
