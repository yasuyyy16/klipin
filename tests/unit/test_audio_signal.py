"""T-035: Sinyal Audio (FR-009). TC-020 dengan fixture audio 25 menit + kasus sintetis."""

from pathlib import Path

import numpy as np
import pytest

from klipin.highlight import audio_signal as a
from klipin.worker.process import JobCancelled

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AUDIO = FIXTURES / "audio_25min_scream_at_10.flac"


def windows(n_seconds: int, size_s: int = 60, step_s: int = 30):
    for start in range(0, max(1, n_seconds - size_s + 1), step_s):
        yield start * 1000, (start + size_s) * 1000


@pytest.fixture(scope="module")
def fixture_signal():
    loud = a.loudness_db_per_second(AUDIO)
    return loud, a.spike_signal(loud)


def test_tc020_scream_window_high_quiet_windows_low(fixture_signal):
    loud, sig = fixture_signal
    assert len(loud) == 1500  # 25 menit, 1 nilai per detik
    assert a.window_signal(sig, 600_000, 660_000) >= 0.8  # jendela menit 10
    assert a.window_signal(sig, 570_000, 630_000) >= 0.8  # jendela geser yang memuat teriakan
    for start, end in windows(len(loud)):
        if end <= 590_000 or start >= 610_000:  # jendela tenang (tidak memuat 10:00–10:03)
            assert a.window_signal(sig, start, end) < 0.3, (start, end)


def test_loudness_range_on_fixture(fixture_signal):
    loud, _ = fixture_signal
    assert loud[:590].max() <= -85  # hening digital
    assert loud[599:604].max() > -25  # semburan keras


def test_quiet_noise_stays_low_and_spike_detected():
    rng = np.random.default_rng(7)
    loud = rng.normal(-35, 0.5, 1500)  # suasana tenang dengan fluktuasi kecil
    loud[900:903] = -10  # teriakan 3 detik di menit 15
    sig = a.spike_signal(loud)
    assert a.window_signal(sig, 900_000, 960_000) >= 0.8
    quiet = [a.window_signal(sig, s, e) for s, e in windows(1500) if e <= 890_000 or s >= 910_000]
    assert max(quiet) < 0.3


def test_rise_mapping_1_sigma_zero_2_sigma_0_8():
    # deret bolak-balik -30/-20 dB: rata-rata -25, simpangan baku 5 dB
    base = np.tile([-30.0, -20.0], 500)
    for sigmas, expected in ((1.0, 0.0), (2.0, 0.8)):
        loud = base.copy()
        loud[-1] = -25 + sigmas * 5  # titik terakhir: kenaikan terhadap 60 detik sebelumnya
        assert a.spike_signal(loud)[-1] == pytest.approx(expected, abs=0.03)
    assert a.spike_signal(np.full(120, -20.0)).max() == 0.0  # konstan: tanpa lonjakan palsu


def test_edges():
    assert a.spike_signal(np.zeros(0)).size == 0
    assert a.window_signal(np.zeros(0), 0, 60_000) == 0.0
    assert a.window_signal(np.array([0.2, 0.9, 0.1]), 1500, 2500) == 0.9  # detik 1–2


def test_video_without_audio_track_gives_no_values():
    assert a.loudness_db_per_second(FIXTURES / "no_audio_10s.mp4").size == 0


def test_range_and_cancel():
    part = a.loudness_db_per_second(AUDIO, start_ms=598_000, end_ms=606_000)
    assert len(part) == 8 and part.max() > -25
    with pytest.raises(JobCancelled):
        a.loudness_db_per_second(AUDIO, should_cancel=lambda: True)
