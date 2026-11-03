"""The master: loudness target, true-peak ceiling, stems that still sum to the mix, seamless
loops."""
import json

import numpy as np
import pytest
import soundfile as sf

from musicengine import loudness, mastering
from musicengine.score import Score

SR = 48000


def _stems(seconds=12, seed=0):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    kick = np.zeros(n)
    for b in np.arange(0, seconds, 0.5):
        i = int(b * SR)
        k = np.exp(-np.arange(4000) / 600) * np.sin(2 * np.pi * 55 * np.arange(4000) / SR)
        kick[i:i + 4000] += k[: n - i]
    pad = 0.1 * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * (1 + 0.5 * np.sin(t))
    hiss = 0.01 * rng.standard_normal(n)
    st = {"kick": np.stack([kick, kick], 1), "pad": np.stack([pad, pad * 0.9], 1), "air": np.stack([hiss, -hiss], 1)}
    return {k: v.astype(np.float32) for k, v in st.items()}


@pytest.mark.parametrize("glue", [True, False])
def test_hits_target_and_ceiling(glue):
    st = _stems()
    mix = sum(st.values())
    out, info = mastering.master(mix, -16.0, -1.0, genre="electronic", glue=glue)
    assert abs(loudness.integrated(out) - (-16.0)) < 0.1
    assert loudness.true_peak_db(out) <= -0.9
    assert info["glue"] is glue


def test_stems_sum_to_the_mix():
    st = _stems()
    mix = sum(st.values())
    gains = {}
    out, _ = mastering.master(mix, -16.0, -1.0, genre="rock", gains=gains)
    total = sum(mastering.master_stem(v, gains) for v in st.values())
    assert np.abs(total - out).max() < 1e-4


def test_stinger_aims_lower():
    st = _stems(seconds=4)
    out, info = mastering.master(sum(st.values()), -16.0, -1.0)
    assert info["target_lufs"] == -18.0
    assert abs(loudness.integrated(out) - (-18.0)) < 0.15


def test_unknown_genre_is_refused():
    with pytest.raises(ValueError):
        mastering.preset("polka-metal")


def test_aliases_resolve():
    assert mastering.preset("house") is mastering.PRESETS["electronic"]


def test_match_eq_moves_balance_toward_reference():
    st = _stems()
    mix = sum(st.values())
    dark = mastering.band_levels(mastering.fx.eq(mix, [("highshelf", 3000, -9)]))
    bands = mastering.match_eq(mix, dark)
    assert bands and all(abs(b[2]) <= 4.0 for b in bands)
    hi = [g for _, f, g, _ in bands if f >= 4000]
    assert hi and max(hi) < 0                     # it cuts the highs toward the darker reference


def _score(stems=False):
    s = Score(bpm=120, bars=8, seed=3, genre="electronic")
    st = _stems(seconds=4)
    s.stem("kick", level_db=-18, reverb=0.1, role="drums")
    s.stem("pad", level_db=-22, reverb=0.4)
    for b in range(0, 8, 2):
        s.audio("kick", st["kick"], b)
        s.audio("pad", st["pad"], b)
    return s


def test_score_loop_render_is_seamless_and_on_target(tmp_path):
    s = _score()
    base = str(tmp_path / "t")
    out, _, _ = s.render(base, stems=True)
    side = json.load(open(base + ".render.json", encoding="utf-8"))
    assert side["master"]["mode"] == "modern" and side["master"]["glue"] is False
    assert abs(side["loudness"]["lufs"] - (-16.0)) < 0.15
    assert side["loudness"]["true_peak_db"] <= -0.9
    stems = [sf.read(str(tmp_path / "t_stems" / f"{n}.wav"), dtype="float32")[0] for n in ("kick", "pad")]
    assert np.abs(sum(stems) - out).max() < 2e-4          # 24-bit files: a few LSB of rounding
    jump = np.abs(out[0] - out[-1]).max()
    near = np.abs(np.diff(np.concatenate([out[-480:], out[:480]]), axis=0)).max()
    assert jump <= near * 1.2


def test_score_leans_toward_a_reference(tmp_path):
    from musicengine import reference
    dark = mastering.fx.eq(sum(_stems(seconds=12).values()), [("highshelf", 3000, -9)])
    sf.write(str(tmp_path / "ref.wav"), dark, SR)
    (tmp_path / "ref.json").write_text(json.dumps(reference.analyze(str(tmp_path / "ref.wav"))))
    s = _score()
    s.reference = str(tmp_path / "ref.json")
    s.render(str(tmp_path / "m"))
    side = json.load(open(tmp_path / "m.render.json", encoding="utf-8"))
    hi = [g for _, f, g, _ in side["master"]["match_eq"] if f >= 4000]
    assert hi and max(hi) < 0
