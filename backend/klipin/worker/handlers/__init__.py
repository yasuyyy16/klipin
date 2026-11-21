"""Registri handler per Jenis Job (`worker/handlers/{job_type}.py`)."""

from collections.abc import Callable

from klipin.config import get_config
from klipin.worker.context import JobContext

Handler = Callable[[JobContext], None]
HANDLERS: dict[str, Handler] = {}


def register(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn
    return deco


def get_handler(job_type: str) -> Handler | None:
    handler = HANDLERS.get(job_type)
    if handler is None and get_config().klipin_providers == "fake":
        from klipin.worker.handlers.fake import fake_handler

        return fake_handler
    return handler


# Handler asli mendaftarkan diri lewat @register saat modulnya diimpor.
from klipin.worker.handlers import download, transcribe  # noqa: F401
