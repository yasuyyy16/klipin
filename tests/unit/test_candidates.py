"""T-039: pemilihan Kandidat Klip — koreksi BR-004, non-overlap BR-005, jumlah BR-006. TC-025."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from klipin.highlight import candidates as c
from klipin.highlight import preselect

HOUR = 3_600_000


def scored_stream(duration_ms: int, seed: int) -> list[c.Scored]:
    rng = random.Random(seed)
    out = []
    for a, b in preselect.window_bounds(0, duration_ms):
        score = rng.randint(0, 100)
        if rng.random() < 0.5:  # setengah jendela punya saran LLM (kadang di luar jendela)
            s0 = rng.uniform(-20, 70)
            out.append(c.Scored(a, b, score, False, s0, s0 + rng.uniform(-5, 120)))
        else:
            out.append(c.Scored(a, b, score, True))
    return out


def assert_valid(chosen, duration_ms, threshold=40, occupied=()):
    assert 1 <= len(chosen) <= 20
    scores = [x.source.score for x in chosen]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= threshold for s in scores)
    ranges = [(x.start_ms, x.end_ms) for x in chosen]
    for i, r in enumerate(ranges):
        assert 15_000 <= r[1] - r[0] <= 90_000
        assert 0 <= r[0] < r[1] <= duration_ms
        for other in [*ranges[i + 1:], *occupied]:
            assert c.overlap(r, other) <= 5_000


def test_tc025_three_hour_stream():
    duration = 3 * HOUR
    chosen = c.select(scored_stream(duration, seed=25), (0, duration), duration, threshold=40)
    assert len(chosen) == 15  # min(20, maks(3, ceil(3 × 5)))
    assert_valid(chosen, duration)


@settings(max_examples=60, deadline=None)
@given(st.integers(20 * 60_000, 8 * HOUR), st.integers(0, 10_000))
def test_select_properties(duration, seed):
    chosen = c.select(scored_stream(duration, seed), (0, duration), duration, threshold=40)
    if chosen:
        assert_valid(chosen, duration)
    assert len(chosen) <= c.max_candidates(duration)


def test_br006_count():
    assert c.max_candidates(10 * 60_000) == 3
    assert c.max_candidates(HOUR) == 5
    assert c.max_candidates(10 * HOUR) == 20
    low = [c.Scored(0, 60_000, 39, True)]
    assert c.select(low, (0, HOUR), HOUR, threshold=40) == []


def test_br004_corrections():
    w = c.Scored(600_000, 660_000, 80, False, 50.0, 58.0)  # 8 dtk → 15 dtk, tetap di jendela
    assert c.correct_range(w, (0, HOUR)) == (645_000, 660_000)
    mid = c.Scored(600_000, 660_000, 80, False, 20.0, 30.0)  # 10 dtk di tengah → simetris
    assert c.correct_range(mid, (0, HOUR)) == (617_500, 632_500)
    out = c.Scored(600_000, 660_000, 80, False, -30.0, 200.0)  # di luar jendela → dijepit
    assert c.correct_range(out, (0, HOUR)) == (600_000, 660_000)
    inverted = c.Scored(600_000, 660_000, 80, False, 40.0, 10.0)
    assert c.correct_range(inverted, (0, HOUR)) == (600_000, 660_000)
    edge = c.Scored(0, 10_000, 80, True)  # jendela pendek di awal stream
    assert c.correct_range(edge, (0, HOUR)) == (0, 15_000)
    tail = c.Scored(HOUR - 10_000, HOUR, 80, True)
    assert c.correct_range(tail, (0, HOUR)) == (HOUR - 15_000, HOUR)
    # rentang transkripsi terbatas (FR-022): tetap di dalamnya
    assert c.correct_range(c.Scored(120_000, 130_000, 80, True), (120_000, 720_000)) == (
        120_000, 135_000)


def test_br005_overlap_keeps_higher_and_respects_reviewed():
    a = c.Scored(0, 60_000, 90, True)
    b = c.Scored(30_000, 90_000, 80, True)  # tumpang tindih 30 dtk dengan a → ditolak
    d = c.Scored(57_000, 117_000, 70, True)  # tumpang tindih 3 dtk → boleh
    chosen = c.select([b, a, d], (0, HOUR), HOUR, 40)
    assert [x.source.score for x in chosen] == [90, 70]
    # rentang Klip yang sudah direview ikut dihindari
    chosen = c.select([a, d], (0, HOUR), HOUR, 40, occupied=[(0, 50_000)])
    assert [x.source.score for x in chosen] == [70]
