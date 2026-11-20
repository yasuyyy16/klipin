"""Tes koneksi API key (FR-021). Penyedia asli menyusul bersama adapternya."""

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
    # shortcut: tes koneksi asli dibuat bersama adapter Deepgram/AssemblyAI (T-028/T-029)
    # dan Anthropic (T-038); sampai saat itu jawab jujur bahwa belum tersedia.
    return {"ok": False, "provider": provider,
            "error": "Tes koneksi untuk penyedia ini belum tersedia di versi ini."}
