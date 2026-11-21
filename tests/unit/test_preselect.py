"""T-037: jendela 60/30 detik + pra-seleksi BR-003 (persentil, sampel acak, batas 120/jam)."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import text

from klipin.highlight import preselect as ps

HOUR = 3_600_000


def windows_with(scores, chat=None):
    return [ps.Window(i * ps.STEP_MS, i * ps.STEP_MS + ps.WINDOW_MS, float(a),
                      None if chat is None else float(chat[i]))
            for i, a in enumerate(scores)]


def test_window_bounds_60_step_30():
    b = ps.window_bounds(0, 150_000)
    assert b == [(0, 60_000), (30_000, 90_000), (60_000, 120_000), (90_000, 150_000)]
    # sisa di akhir dipotong; < 15 detik tidak dibuat
    assert ps.window_bounds(0, 100_000)[-1] == (60_000, 100_000)
    assert ps.window_bounds(0, 95_000)[-1] == (60_000, 95_000)
    assert ps.window_bounds(0, 70_000) == [(0, 60_000), (30_000, 70_000)]
    assert ps.window_bounds(0, 10_000) == [(0, 10_000)]  # stream sangat pendek: tetap 1 jendela
    # rentang transkripsi (FR-022): jendela hanya di dalamnya
    assert ps.window_bounds(120_000, 240_000)[0] == (120_000, 180_000)
    assert len(ps.window_bounds(0, HOUR)) == 119


def test_percentile_80_plus_random_5_percent():
    scores = np.linspace(0, 1, 100)
    ws = windows_with(scores)
    chosen = ps.preselect(ws, 50 * 60_000 + 30_000, seed=7)
    top = [w for w in ws if w.pre_score >= np.percentile(scores, 80)]
    assert len(top) == 20
    assert all(w.preselected for w in top)
    extra = [w for w in chosen if w not in top]
    assert len(extra) == 4  # ceil(80 × 5%)
    assert all(w.pre_score < np.percentile(scores, 80) for w in extra)
    assert sum(w.preselected for w in ws) == 24
    assert chosen[0].pre_score == 1.0  # urut prioritas: skor tertinggi dulu


def test_random_sample_is_deterministic_per_stream():
    a = [w.start_ms for w in ps.preselect(windows_with(np.linspace(0, 1, 100)), HOUR, seed=3)]
    b = [w.start_ms for w in ps.preselect(windows_with(np.linspace(0, 1, 100)), HOUR, seed=3)]
    c = [w.start_ms for w in ps.preselect(windows_with(np.linspace(0, 1, 100)), HOUR, seed=4)]
    assert a == b and a != c


def test_chat_weighting_and_missing_chat():
    w = ps.Window(0, 60_000, 0.5, 1.0)
    assert w.pre_score == pytest.approx(0.7)  # 0,6×0,5 + 0,4×1
    assert ps.Window(0, 60_000, 0.5, None).pre_score == 0.5


def test_tc024_spikes_everywhere_capped_at_120_per_hour():
    ws = windows_with(np.ones(119))  # semua jendela sama tinggi: semua ≥ persentil 80
    chosen = ps.preselect(ws, HOUR, seed=1)
    assert len(chosen) <= 120
    # rapat (langkah 10 dtk) agar jumlah jendela melebihi batas
    dense = [ps.Window(i * 10_000, i * 10_000 + 60_000, 1.0, None) for i in range(354)]
    assert len(ps.preselect(dense, HOUR, seed=1)) == 120
    assert ps.max_windows(30 * 60_000) == 60 and ps.max_windows(90 * 60_000) == 180


@given(st.lists(st.floats(0, 1), min_size=1, max_size=400), st.integers(1, 10 * HOUR),
       st.integers(0, 1000))
def test_preselect_properties(scores, duration_ms, seed):
    ws = windows_with(scores)
    chosen = ps.preselect(ws, duration_ms, seed)
    assert 1 <= len(chosen) <= ps.max_windows(duration_ms)
    assert sum(w.preselected for w in ws) == len(chosen)
    assert len({id(w) for w in chosen}) == len(chosen)


def test_build_windows_uses_signals():
    audio = np.zeros(180)
    audio[95] = 1.0
    chat = np.zeros(18)
    chat[9] = 0.5
    ws = ps.build_windows(0, 180_000, audio, chat)
    by_start = {w.start_ms: w for w in ws}
    assert by_start[60_000].audio == 1.0 and by_start[0].audio == 0.0
    assert by_start[60_000].chat == 0.5
    assert all(w.chat is None for w in ps.build_windows(0, 180_000, audio, None))


def test_store_keeps_llm_cache(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO source_streams (id, source_type, platform, source_url, "
                          "title, status) VALUES (1, 'vod_url', 'youtube', 'https://youtu.be/x', "
                          "'S', 'processing')"))
        ws = windows_with([0.1, 0.9, 0.2])
        for w, flag in zip(ws, (False, True, False), strict=True):
            w.preselected = flag
        ps.store(conn, 1, ws)
        conn.execute(text("UPDATE highlight_windows SET llm_score = 77, llm_status = 'done' "
                          "WHERE start_ms = 30000"))
        ws[1].audio = 0.95
        ps.store(conn, 1, ws[:2])  # jendela ketiga hilang (rentang berubah)
        rows = conn.execute(text("SELECT start_ms, audio_signal, preselected, llm_score, "
                                 "llm_status FROM highlight_windows ORDER BY start_ms")).all()
    assert rows == [(0, 0.1, 0, None, "not_requested"), (30_000, 0.95, 1, 77, "done")]
