"""Perkiraan pemakaian API & penahanan Job `transcribe` (FR-022).

- Ditahan (`awaiting_confirmation = 1`) bila durasi > `confirm_usage_over_min` menit
  (`null` = konfirmasi mati, `0` = selalu), **atau** durasi > `max_audio_minutes_per_job`
  (batas ini tetap berlaku walau konfirmasi mati).
- Jendela LLM diperkirakan dari batas BR-003: maks. 120 jendela per jam stream.
- Harga tidak pernah ditampilkan; hanya tautan halaman harga resmi (07-integrasi.md).
"""

import json
from typing import Any

from sqlalchemy import Connection, text

from klipin.config import get_config

LLM_WINDOWS_PER_HOUR = 120  # BR-003
HOUR_MS = 3_600_000
# Halaman harga resmi (dicek 2026-11-21; 07-integrasi.md §"Tautan harga").
PRICING_LINKS = {
    "deepgram": "https://deepgram.com/pricing",
    "assemblyai": "https://www.assemblyai.com/pricing",
    "anthropic": "https://claude.com/pricing#api",
}


def _setting(conn: Connection, key: str) -> Any:
    raw = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).scalar()
    try:
        return json.loads(raw) if raw is not None else None
    except ValueError:
        return None


def limits(conn: Connection) -> tuple[int | None, int]:
    """(ambang konfirmasi ms atau None bila mati, batas audio per Job ms)."""
    over_min = _setting(conn, "confirm_usage_over_min")
    max_min = _setting(conn, "max_audio_minutes_per_job") or 600
    return (None if over_min is None else int(over_min) * 60_000), int(max_min) * 60_000


def needs_confirmation(conn: Connection, duration_ms: int | None) -> bool:
    if duration_ms is None:  # durasi belum diketahui: tidak bisa diperkirakan
        return False
    threshold, max_ms = limits(conn)
    return duration_ms > max_ms or (threshold is not None and duration_ms > threshold)


def format_duration(ms: int) -> str:
    """Durasi untuk teks UI: "2 jam 10 menit", "45 menit", "30 detik"."""
    total_s = round(ms / 1000)
    h, m = total_s // 3600, total_s % 3600 // 60
    if not h and not m:
        return f"{total_s} detik"
    return " ".join(p for p in (f"{h} jam" if h else "", f"{m} menit" if m else "") if p)


def estimated_llm_windows(audio_ms: int) -> int:
    """Dibulatkan biasa (minimal 1): ceil membuat 30,03 detik menjadi 2 jendela."""
    return max(1, round(audio_ms / HOUR_MS * LLM_WINDOWS_PER_HOUR)) if audio_ms > 0 else 0


def usage_estimate(conn: Connection, stream_id: int, range_ms: dict | None) -> dict[str, Any]:
    duration = conn.execute(text("SELECT duration_ms FROM source_streams WHERE id = :s"),
                            {"s": stream_id}).scalar() or 0
    audio_ms = range_ms["end_ms"] - range_ms["start_ms"] if range_ms else duration
    _, max_ms = limits(conn)
    cfg = get_config()
    transcriber = _setting(conn, "transcriber_provider") or cfg.klipin_transcriber
    llm = _setting(conn, "llm_provider") or cfg.klipin_llm_provider
    return {
        "audio_ms": audio_ms,
        "estimated_llm_windows": estimated_llm_windows(audio_ms),
        "duration_ms": duration,
        "max_audio_ms": max_ms,
        "over_limit": audio_ms > max_ms,
        "pricing_links": {"transcriber": PRICING_LINKS.get(transcriber),
                          "llm": PRICING_LINKS.get(llm)},
    }
