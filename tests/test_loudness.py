"""BS.1770 / EBU R128 conformance on the EBU Tech 3341/3342 style test signals."""
import numpy as np

from musicengine import loudness
from conftest import sine


def test_stereo_1k_sine_at_minus_23_reads_minus_23_lufs():
    assert abs(loudness.integrated(sine(1000, 20, -23)) - (-23.0)) < 0.1


def test_relative_gate_ignores_quiet_parts():
    # EBU 3341 case 3: -36 / -23 / -36 dBFS for 10/60/10 s -> -23 LUFS
    x = np.concatenate([sine(1000, 10, -36), sine(1000, 60, -23), sine(1000, 10, -36)])
    assert abs(loudness.integrated(x) - (-23.0)) < 0.1


def test_silence_is_gated_out():
    assert loudness.integrated(np.zeros((48000 * 5, 2), np.float32)) < -150


def test_lra_of_two_levels_ten_db_apart():
    # EBU 3342 case 1: -20 then -30 dBFS, 20 s each -> LRA 10 LU
    x = np.concatenate([sine(1000, 20, -20), sine(1000, 20, -30)])
    assert abs(loudness.lra(x) - 10.0) < 0.2


def test_true_peak_finds_the_peak_between_samples():
    n = np.arange(48000)
    x = np.sin(2 * np.pi * 12000 * n / 48000 + np.pi / 4)        # samples peak at 0.707, signal at 1.0
    x = np.stack([x, x], axis=1)
    assert np.abs(x).max() < 0.71
    assert -0.4 < loudness.true_peak_db(x) < 0.3                  # EBU 3341 tolerance +0.2/-0.4


def test_measure_returns_all_fields():
    m = loudness.measure(sine(1000, 5, -20))
    assert set(m) == {"lufs", "lra", "true_peak_db", "plr"}
