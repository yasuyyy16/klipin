"""Log JSON terstruktur ke {KLIPIN_HOME}/logs/klipin.log dengan penyamaran rahasia (NFR-005)."""

import logging
import re
import sys
from typing import Any

import structlog
from concurrent_log_handler import ConcurrentRotatingFileHandler

from klipin.config import Config

MASK = "***"

# Nilai setelah nama kunci yang sensitif, mis. api_key=..., "token": "...", ?t=...
_KEY_VALUE = re.compile(
    r"""(?ix)
    (\b(?:[a-z_-]*api[_-]?key|[a-z_-]*token|[a-z_-]*secret|password|authorization)
       ["']?\s*[:=]\s*["']?(?:bearer\s+|token\s+)?)
    [^\s"'&,;}]+
    |([?&]t=)[^\s"'&]+
    """
)
# Bentuk token yang dikenali walau tanpa nama kunci.
_TOKEN_SHAPES = re.compile(
    r"""(?x)
    \bBearer\s+[\w.~+/-]+=*
    |\bsk-[\w-]{16,}            # Anthropic / gaya OpenAI
    |\bGOCSPX-[\w-]+            # Google client secret
    |\bya29\.[\w.-]+            # Google access token
    |\b1//[\w-]{20,}            # Google refresh token
    |\bEAA[A-Za-z0-9]{20,}      # Meta access token
    |\b(?:act|rft)\.[\w.-]{20,} # TikTok access/refresh token
    |\b[a-fA-F0-9]{32,}\b       # key hex panjang (Deepgram, AssemblyAI)
    """
)


def mask_secrets(text: str) -> str:
    text = _KEY_VALUE.sub(lambda m: (m.group(1) or m.group(2)) + MASK, text)
    return _TOKEN_SHAPES.sub(MASK, text)


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask(v) for v in value]
    return value


def _mask_processor(_logger: Any, _method: str, event_dict: dict) -> dict:
    return {k: _mask(v) for k, v in event_dict.items()}


def setup_logging(cfg: Config, process: str) -> None:
    log_dir = cfg.klipin_home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            _mask_processor,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    file_handler = ConcurrentRotatingFileHandler(
        log_dir / "klipin.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        keep_file_open=False,  # API & Worker menulis file yang sama
    )
    console = logging.StreamHandler(sys.stderr)
    for h in (file_handler, console):
        h.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [file_handler, console]
    root.setLevel(cfg.klipin_log_level)

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(process=process)
