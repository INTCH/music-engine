"""The performance layer on a stand-in instrument whose notes swell in slowly, like recorded
string sustains do (no samples needed)."""
import random

import numpy as np
import pytest

from musicengine import perform
from musicengine.score import Score

SR = 48000


class SlowBow:
    """Sine notes with a 300 ms swell-in and a short cos^2 release, level by velocity."""
    roots = np.array([36, 96])

    def render(self, midi, dur, vel=0.7, rng=None, attack=None, release=0.15, cents=0.0, near=None):
        n = int((dur + release) * SR)
        t = np.arange(n) / SR
        f = 440 * 2 ** ((midi - 69 + cents / 100) / 12)
        x = np.sin(2 * np.pi * f * t) * (0.2 + 0.6 * vel)
        env = np.minimum(1, t / 0.3) ** 2
        rs = int(dur * SR)
        env[rs:] *= np.cos(np.linspace(0, np.pi / 2, n - rs)) ** 2
        x = (x * env).astype(np.float32)
        return np.stack([x, x], axis=1)


def _hole_db(x, t0, onsets):
    m = x.mean(axis=1)

    def lev(a, b):
        return 10 * np.log10((m[max(0, a):b] ** 2).mean() + 1e-12)
    out = []
    for t in onsets:
        c = int((t - t0) * SR)
        around = 0.5 * lev(c - int(0.4 * SR), c - int(0.1 * SR)) + 0.5 * lev(c + int(0.25 * SR), c + int(0.55 * SR))
        out.append(around - lev(c, c + int(0.15 * SR)))
    return float(np.mean(out))


def _items():
    return [(i * 0.8, 0.8, m, 0.6, {}) for i, m in enumerate([60, 62, 64, 65, 67, 65, 64, 62])]


def test_legato_fills_the_hole_a_slow_attack_leaves():
    items = _items()
    plain, t0p = perform.render_line(SlowBow(), items, random.Random(1), legato=False)
    leg, t0l = perform.render_line(SlowBow(), items, random.Random(1), legato=True)
    onsets = [it[0] for it in items[1:]]
    assert _hole_db(plain, t0p, onsets) > 2.0
    assert abs(_hole_db(leg, t0l, onsets)) < 1.0


def test_legato_keeps_timing_and_length():
    items = _items()
    x, t0 = perform.render_line(SlowBow(), items, random.Random(1), legato=True)
    assert abs(t0 - (0 - 0)) < 1e-9                                   # first note isn't moved
    end = items[-1][0] + items[-1][1] + 0.15
    assert abs(len(x) / SR + t0 - end) < 0.05


def test_rest_breaks_the_legato():
    items = [(0.0, 0.8, 60, 0.6, {}), (1.6, 0.8, 62, 0.6, {})]       # 0.8 s rest between
    a, _ = perform.render_line(SlowBow(), items, random.Random(1), legato=True)
    b, _ = perform.render_line(SlowBow(), items, random.Random(1), legato=False)
    assert np.array_equal(a, b)


def test_swell_follows_its_curve():
    x = perform.render_note(SlowBow(), 69, 2.0, 0.8, random.Random(1), swell="cresc")

    def lev(a, b):
        return 10 * np.log10((x[int(a * SR):int(b * SR)] ** 2).mean())
    assert lev(1.6, 1.9) - lev(0.3, 0.6) > 2.0


def test_flat_swell_is_a_plain_note():
    a = perform.render_note(SlowBow(), 69, 1.0, 0.7, random.Random(1), swell="flat")
    b = SlowBow().render(69, 1.0, 0.7)
    assert np.allclose(a, b)


def test_phrase_arches_tapers_and_relaxes():
    notes = [(i, 1.0, m, 0.6, {}) for i, m in enumerate([60, 62, 64, 67, 64, 62, 60])]
    out = perform.phrase(notes)
    vels = [n[3] for n in out]
    assert vels[3] == max(vels)                       # the high note leads
    assert vels[-1] < vels[-2]                        # the end tapers
    assert out[-1][0] > notes[-1][0]                  # the last onset relaxes late
    for a, b in zip(out, out[1:]):                    # still joined end to start
        assert abs(a[0] + a[1] - b[0]) < 1e-9


def test_phrase_splits_at_rests():
    notes = [(0, 1, 60, .6, {}), (1, 1, 72, .6, {}), (4, 1, 60, .6, {}), (5, 1, 72, .6, {})]
    out = perform.phrase(notes)
    assert out[1][3] < out[0][3] or out[1][0] > 1    # first phrase ends (taper/relax) before the rest
    assert out[2][0] == 4                             # second phrase starts on time


def test_score_line_renders_and_exports_midi(tmp_path, monkeypatch):
    from musicengine import score as score_mod
    monkeypatch.setattr(score_mod, "get", lambda name: SlowBow())
    monkeypatch.setattr(score_mod.catalog, "synthetic", lambda name: None)
    s = Score(bpm=90, bars=4, seed=2, loop=False, tail=2.0)
    s.stem("lead", level_db=-20, reverb=0.2)
    s.line("lead", "slowbow", [(0, 0, 2, 64, .6), (0, 2, 2, 67, .6), (1, 0, 4, 69, .6, {"swell": "dim"}),
                                (2, 0, 4, 67, .6)])
    out, _, _ = s.render(str(tmp_path / "l"), midi=True)
    assert np.abs(out).max() > 0
    from musicengine import midi
    assert len(midi.read(str(tmp_path / "l.mid")).notes) == 4


@pytest.mark.parametrize("name", sorted(perform.SWELLS))
def test_named_swells_are_valid(name):
    pts = perform.SWELLS[name]
    assert pts[0][0] == 0.0 and pts[-1][0] == 1.0
    assert all(0 < lv <= 1 for _, lv in pts)
