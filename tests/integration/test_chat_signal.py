"""T-036: Sinyal Chat (FR-010) + pembagian bobot tanpa chat (BR-002). TC-021, TC-022."""

from pathlib import Path

import pytest
from sqlalchemy import text

from klipin.highlight import chat_signal as cs
from klipin.highlight.scoring import Score, Weights, combine, without_chat
from klipin.worker.handlers.download import import_chat

CHAT = Path(__file__).resolve().parents[1] / "fixtures" / "live_chat_spike.jsonl"
DURATION = 1_200_000  # fixture chat 20 menit
DEFAULT = Weights(0.30, 0.20, 0.50)


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO source_streams (id, source_type, platform, source_url, "
                          "title, status, duration_ms) VALUES (1, 'vod_url', 'youtube', "
                          "'https://youtu.be/x', 'Chat', 'processing', :d)"), {"d": DURATION})
    assert import_chat(engine, 1, CHAT) == 250
    return engine


def signal(engine):
    with engine.connect() as conn:
        return cs.stream_chat_signal(conn, 1, DURATION)


def set_setting(engine, key, value):
    with engine.begin() as conn:
        conn.execute(text("UPDATE settings SET value = :v WHERE key = :k"), {"k": key, "v": value})


def test_tc021_peak_shifted_by_chat_delay(db):
    sig = signal(db)
    assert len(sig) == DURATION // cs.BUCKET_MS
    peak = int(sig.argmax())
    peak_center_s = (peak * cs.BUCKET_MS + cs.BUCKET_MS // 2) / 1000
    assert abs(peak_center_s - 592) <= 10  # lonjakan detik 600 − Jeda Chat 8 detik
    assert sig[peak] == 1.0
    quiet = [v for i, v in enumerate(sig) if not 57 <= i <= 61]
    assert max(quiet) < 0.3
    # jendela 60 detik yang memuat detik 592 punya Sinyal Chat tertinggi
    windows = {s: cs.window_signal(sig, s * 1000, (s + 60) * 1000) for s in range(0, 1141, 30)}
    best = max(windows, key=windows.get)
    assert best <= 592 < best + 60


def test_chat_delay_setting_is_used(db):
    set_setting(db, "chat_delay_ms", "0")
    assert int(signal(db).argmax()) == 60  # tanpa jeda: ember 600–610 detik


def test_reaction_weight_follows_current_settings(db):
    base = cs.bucket_counts([(600_000, True), (601_000, False)], 700_000, delay_ms=0)
    assert base[60] == 2.5  # 1,5 + 1
    # daftar kata reaksi dikosongkan → pesan lonjakan berbobot 1, puncak tetap di tempat sama
    set_setting(db, "chat_reaction_words", "[]")
    assert int(signal(db).argmax()) == 59


def test_negative_offsets_ignored_and_median_floor():
    counts = cs.bucket_counts([(-5000, False), (3000, False)], 60_000, delay_ms=8000)
    assert counts.sum() == 0  # keduanya < 0 setelah digeser
    sig = cs.spike_signal(cs.bucket_counts([(15_000, False)], 300_000, delay_ms=0))
    assert sig.max() == 0.0  # 1 pesan di tengah chat sepi (median 0 → lantai 1 pesan)


def test_tc022_no_chat_signal_and_weights_redistributed(db):
    with db.begin() as conn:
        conn.execute(text("UPDATE source_streams SET has_chat = 0"))
    assert signal(db) is None
    assert cs.window_signal(None, 0, 60_000) is None
    w = without_chat(DEFAULT)
    assert w.chat == 0.0
    assert w.audio == pytest.approx(0.375) and w.llm == pytest.approx(0.625)
    assert w.audio + w.llm == pytest.approx(1.0)
    # skor tetap terhitung dari audio + LLM
    assert combine(0.8, None, 60, DEFAULT) == Score(68, False)  # 100×(0,375×0,8 + 0,625×0,6)


def test_br001_full_and_partial_scores():
    assert combine(1.0, 1.0, 100, DEFAULT) == Score(100, False)
    assert combine(0.5, 0.5, 50, DEFAULT) == Score(50, False)
    assert combine(0.8, 0.5, 70, DEFAULT) == Score(69, False)  # 24 + 10 + 35
    # LLM null → hanya audio + chat, dinormalkan ulang, ditandai parsial
    assert combine(0.8, 0.5, None, DEFAULT) == Score(68, True)  # (0,24 + 0,10) / 0,5
    assert combine(0.8, None, None, DEFAULT) == Score(80, True)
    assert without_chat(Weights(0, 1, 0)) == Weights(0.5, 0, 0.5)
