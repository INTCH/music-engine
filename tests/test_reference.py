"""Reference analysis on signals whose answer is known."""
import json

import numpy as np
import soundfile as sf

from musicengine import reference

SR = 48000


def _clicks(bpm, seconds=30):
    n = int(seconds * SR)
    x = np.zeros(n)
    burst = np.random.default_rng(1).standard_normal(400) * np.exp(-np.arange(400) / 80)
    for t in np.arange(0, seconds, 60 / bpm):
        i = int(t * SR)
        x[i:i + 400] += burst[: n - i]
    return np.stack([x, x], 1).astype(np.float32) * 0.3


def _chords(pcs_list, seconds_each=4):
    out = []
    for pcs in pcs_list:
        t = np.arange(int(seconds_each * SR)) / SR
        y = sum(np.sin(2 * np.pi * 440 * 2 ** ((p - 9) / 12) * t) for p in pcs) * 0.1
        out.append(y)
    y = np.concatenate(out)
    return np.stack([y, y], 1).astype(np.float32)


def test_tempo_of_a_click_track():
    for bpm in (84, 112, 128):
        est, conf, alts = reference.tempo(_clicks(bpm).mean(axis=1))
        assert abs(est - bpm) < 1.0 or any(abs(a - bpm) < 1.0 for a in alts), (bpm, est, alts)


def test_key_of_a_minor_progression():
    # i iv V i in D minor: Dm Gm A Dm
    x = _chords([[2, 5, 9], [7, 10, 2], [9, 1, 4], [2, 5, 9], [2, 5, 9]])
    tonic, mode, margin, _ = reference.key(x.mean(axis=1))
    assert (tonic, mode) == ("D", "minor")


def test_key_of_a_major_progression():
    x = _chords([[7, 11, 2], [0, 4, 7], [2, 6, 9], [7, 11, 2], [7, 11, 2]])
    tonic, mode, _, _ = reference.key(x.mean(axis=1))
    assert (tonic, mode) == ("G", "major")


def test_analyze_writes_everything_and_compare_runs(tmp_path):
    x = _clicks(100, 30) + _chords([[9, 0, 4]] * 8, 30 / 8)[: int(30 * SR)]
    p = tmp_path / "ref.wav"
    sf.write(str(p), x, SR)
    d = reference.analyze(str(p))
    for k in ("tempo", "key", "loudness", "bands", "tilt_db_per_octave", "stereo", "centroid_hz",
              "onsets_per_second", "sections_s", "energy_lufs_per_s"):
        assert k in d
    assert len(d["bands"]) == len(d["band_centers_hz"])
    (tmp_path / "ref.json").write_text(json.dumps(d))
    c = reference.compare(str(p), str(tmp_path / "ref.json"))
    assert all(abs(delta) < 1e-6 for _, _, _, delta in c["rows"])


def test_resamples_other_rates(tmp_path):
    x = _clicks(120, 10)[::1]
    p = tmp_path / "r44.wav"
    from scipy.signal import resample_poly
    sf.write(str(p), resample_poly(x, 147, 160, axis=0), 44100)
    y = reference.load(str(p))
    assert abs(len(y) - len(x)) < 10
