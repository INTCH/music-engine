"""The Score clock: loop renders keep LFO effects phase-continuous across the seam, one-shots
keep the exact rates, and stem automation (sweep points, duck times) is score time."""
import numpy as np
import pytest

from musicengine import fx
from musicengine.analyze import seam
from musicengine.engine import hall_ir
from musicengine.score import Score

SR = 48000
LFO_FX = [("chorus", {"rate": 0.77, "depth_ms": 6, "mix": 0.6}), ("tremolo", {"rate": 3.3, "depth": 0.6}),
          ("tape", {"wow": 0.004, "wow_hz": 0.45}), ("flanger", {"rate": 0.31}), ("phaser", {"rate": 0.37}),
          ("leslie", {"speed": "slow"})]


def _tone(seconds, freqs=(220.0, 330.0)):
    t = np.arange(int(seconds * SR)) / SR
    x = sum(0.1 * np.sin(2 * np.pi * f * t) for f in freqs)
    return np.stack([x, x], axis=1).astype(np.float32)


def _loop_score(fx_chain=None, autopan=(0.13, 0.8), loop=True):
    s = Score(bpm=120, bars=4, seed=1, loop=loop)     # L = 8 s, rates above are off-grid
    s.stem("pad", level_db=-20, reverb=0.0, autopan=autopan, fx=fx_chain)
    for b in range(4):
        s.audio("pad", _tone(2.0), b)       # one bar each, so the dry stem repeats every loop
    s.place_all()
    return s


def test_loop_rate_rounds_to_whole_cycles():
    assert fx.loop_rate(0.77, 8.0) == 6 / 8.0
    assert fx.loop_rate(0.01, 8.0) == 1 / 8.0          # at least one cycle per loop
    assert fx.loop_rate(0.77, None) == 0.77


@pytest.mark.parametrize("name,params", LFO_FX + [("autopan", None)])
def test_loop_modulation_meets_itself_at_the_seam(name, params):
    """The buffer one loop after the cycle start must repeat the cycle start: the cut loop
    then continues into itself. Without the clock, chorus/autopan phase would drift by rate*L."""
    s = _loop_score(fx_chain=None if name == "autopan" else [(name, params)],
                    autopan=(0.13, 0.8) if name == "autopan" else None)
    out = s.mix.render(hall_ir(1.0))[0]
    a, L, w = int(s.pre * SR), int(s.L * SR), int(1.0 * SR)
    head, wrap = out[a:a + w], out[a + L:a + L + w]
    assert np.abs(wrap - head).max() < 0.02 * np.abs(head).max()


def test_loop_render_passes_the_seam_check(tmp_path):
    s = _loop_score(fx_chain=[("chorus", {"rate": 0.77, "depth_ms": 6, "mix": 0.6})])
    out, _, _ = s.render(str(tmp_path / "l"))
    assert seam(out, SR)["ok"]


def test_one_shot_keeps_exact_rates():
    s = _loop_score(loop=False)
    assert s.mix.clock["period"] is None
    x = _tone(3.0)
    assert np.array_equal(fx.chain(x, [("chorus", {"rate": 0.77})], clock=s.mix.clock), fx.chorus(x, rate=0.77))


def test_duck_times_are_score_time():
    s = Score(bpm=120, bars=4, seed=1, loop=False)
    s.stem("pad", level_db=-20, reverb=0.0, fx=[("duck", {"times": [s.t(2)], "depth_db": -30})])
    s.audio("pad", _tone(8.0), 0)
    s.place_all()
    out = s.mix.render(hall_ir(1.0))[0]
    env = np.abs(out[:, 0]).reshape(-1, 480).max(axis=1)        # 10 ms blocks
    a = int((s.pre + 0.05) * SR / 480)                           # past the silent pre-roll
    dip = (a + np.argmin(env[a: int(8 * SR / 480)])) * 480 / SR
    assert abs(dip - (s.pre + s.t(2))) < 0.05


def test_duck_times_repeat_each_loop():
    s = Score(bpm=120, bars=4, seed=1)
    s.stem("pad", level_db=-20, reverb=0.0, fx=[("duck", {"times": [0.0], "depth_db": -30})])
    for b in range(4):
        s.audio("pad", _tone(2.0), b)
    s.place_all()
    out = s.mix.render(hall_ir(1.0))[0]
    a, L = int(s.pre * SR), int(s.L * SR)
    k = int(0.05 * SR)
    quiet = np.abs(out[a + L + 480:a + L + k]).max()        # the next cycle's downbeat duck
    loud = np.abs(out[a + L // 2:a + L // 2 + k]).max()
    assert quiet < 0.2 * loud


def test_sweep_points_are_score_time_and_wrap():
    x = _tone(20.0, freqs=(4000.0,))
    pts = [(0.0, 200.0), (4.0, 200.0), (4.01, 16000.0), (7.9, 16000.0)]
    y = fx.sweep(x, points=pts, offset=2.0, period=8.0)
    lvl = lambda t0: np.abs(y[int(t0 * SR):int((t0 + 0.2) * SR)]).max()
    assert lvl(2.0 + 1.0) < 0.1 * lvl(2.0 + 5.0)              # closed before score 4 s, open after
    assert lvl(2.0 + 9.0) < 0.1 * lvl(2.0 + 13.0)             # and again in the next cycle
    assert lvl(1.0) > 0.5 * lvl(2.0 + 5.0)                    # the pre-roll is the previous cycle's end
