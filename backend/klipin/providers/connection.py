"""Tes koneksi API key (FR-021). Penyedia asli ditambahkan bersama adapternya."""

import time

from klipin.config import get_config

TIMEOUT_S = 10  # 06-api.md §4


def test_connection(provider: str, value: str) -> dict:
    if get_config().klipin_providers == "fake":
        start = time.perf_counter()
        # Penyedia palsu: key berawalan "invalid" dianggap ditolak, untuk menguji UI gagal.
        if value.startswith("invalid"):
            return {"ok": False, "provider": provider, "error": "401 invalid api key"}
        return {"ok": True, "provider": provider,
                "latency_ms": int((time.perf_counter() - start) * 1000)}
    if provider in ("deepgram", "assemblyai"):
        from klipin.providers.transcriber import TranscriberError, assemblyai, deepgram

        start = time.perf_counter()
        try:
            (deepgram if provider == "deepgram" else assemblyai).test_key(value)
        except TranscriberError as e:
            detail = getattr(e, "detail", "")
            return {"ok": False, "provider": provider,
                    "error": f"{e} ({detail})" if detail else str(e)}
        return {"ok": True, "provider": provider,
                "latency_ms": int((time.perf_counter() - start) * 1000)}
    if provider == "anthropic":
        import anthropic

        from klipin.providers.llm import anthropic_judge

        start = time.perf_counter()
        try:
            anthropic_judge.test_key(value)
        except anthropic.AuthenticationError:
            return {"ok": False, "provider": provider,
                    "error": "API key LLM ditolak penyedia (401)."}
        except anthropic.APIError as e:
            return {"ok": False, "provider": provider,
                    "error": f"Tes koneksi gagal: {type(e).__name__}"}
        return {"ok": True, "provider": provider,
                "latency_ms": int((time.perf_counter() - start) * 1000)}
    return {"ok": False, "provider": provider,
            "error": "Tes koneksi untuk penyedia ini belum tersedia di versi ini."}
