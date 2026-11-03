"""Instrument behaviour: sub-program sample paths, CC-gated SFZ regions, level across velocity
layers, late bowed attacks, sfizz velocity response, and the VCSL glockenspiel's pitch offset.
Sample-free tests build tiny instruments from generated WAVs; `samples` tests use the library."""
import random

import numpy as np
import pytest
import soundfile as sf

from musicengine import catalog, engine, sfz
from musicengine.engine import Instrument
from musicengine.external import ExternalInstrument

SR = 48000


@pytest.fixture(autouse=True)
def _levels_cache(tmp_path, monkeypatch):
    """Keep sample-free tests from writing into the library's levels cache."""
    monkeypatch.setattr(engine, "_levels_path", lambda: tmp_path / "levels.json")


def _wav(path, freq=440.0, seconds=2.0, db=-20.0, swell=0.0):
    t = np.arange(int(seconds * SR)) / SR
    x = 10 ** (db / 20) * np.sin(2 * np.pi * freq * t)
    if swell:
        x *= np.minimum(1.0, t / swell) ** 2
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.stack([x, x], axis=1), SR)
    return str(path)


def _db(x, a=0.1, b=0.9):
    seg = x[int(a * SR):int(b * SR)]
    return 10 * np.log10((seg ** 2).mean() + 1e-12)


# ---------------------------------------------------------------- 1. sub-program paths

def test_subprogram_samples_resolve_from_the_parent_folder(tmp_path):
    """Programs/mappings/ride/sub.sfz says sample=../Samples/hit.wav, which only makes sense
    from Programs/ (where the parent program lives)."""
    lib = tmp_path / "lib"
    _wav(lib / "Samples" / "hit.wav")
    sub = lib / "Programs" / "mappings" / "ride" / "sub.sfz"
    sub.parent.mkdir(parents=True)
    sub.write_text("<group> hivel=63\n<region> sample=../Samples/hit.wav\n")
    assert sfz.zones(str(sub), lib_root=str(lib)) != []
    z = sfz.zones(str(sub), lib_root=str(lib))[0]
    assert z["path"] == str(lib / "Samples" / "hit.wav")
    assert z["keytrack"] is False          # no key: the parent assigns one; plays unpitched
    # never looks above the library folder
    assert sfz.zones(str(sub), lib_root=str(sub.parent)) == []


def test_keyed_regions_still_track_pitch(tmp_path):
    p = tmp_path / "inst.sfz"
    _wav(tmp_path / "a.wav")
    p.write_text("<region> sample=a.wav lokey=60 hikey=72 pitch_keycenter=69\n")
    assert sfz.zones(str(p))[0]["keytrack"] is True


@pytest.mark.samples
@pytest.mark.parametrize("name", ["karoryfer-big-rusty-drums/rd-brush-cl", "karoryfer-big-rusty-drums/sn-brush-oh",
                                  "karoryfer-frankensnare/10-basic-btm"])
def test_drum_subprograms_make_sound(name):
    inst = catalog.get(name)
    x = inst.render(60, 0.5, 0.6, rng=random.Random(1))
    y = inst.render(48, 0.5, 0.6, rng=random.Random(1))
    assert np.abs(x).max() > 1e-3
    assert np.array_equal(x, y)            # a hit, not a pitched note


# ---------------------------------------------------------------- CC-gated regions

def test_regions_gated_by_a_controller_follow_its_start_value(tmp_path):
    for n in "abc":
        _wav(tmp_path / f"{n}.wav")
    p = tmp_path / "gated.sfz"
    p.write_text("<control> set_cc20=10\n"
                 "<region> sample=a.wav hicc107=15\n"          # cc107 defaults to 0: on
                 "<region> sample=b.wav locc107=16\n"          # off
                 "<region> sample=c.wav locc20=0 hicc20=5\n")  # set_cc20=10: off
    assert [z["path"][-5:] for z in sfz.zones(str(p))] == ["a.wav"]
    # a sub-program whose every region needs a CC the parent sets: keep them all
    q = tmp_path / "sub.sfz"
    q.write_text("<region> sample=a.wav locc107=16\n<region> sample=b.wav locc107=16 locc5=$X\n")
    assert len(sfz.zones(str(q))) == 2


@pytest.mark.samples
def test_bigcat_cello_bowed_patch_has_no_staccato_or_voice_copies():
    inst = catalog.get("karoryfer-bigcat-cello/01-bowed-velocity-layer")
    assert not any("staccato" in z["path"].lower() for z in inst.zones)
    assert len(inst.zones) < 200


# ---------------------------------------------------------------- 2. level across layers

def _layered(tmp_path):
    """Two layers recorded 20 dB apart; one soft note recorded 12 dB too loud."""
    zones = []
    for root in (60, 64, 67, 72):
        loud_soft = -32.0 + (12.0 if root == 67 else 0.0)
        zones.append((_wav(tmp_path / f"s{root}.wav", 440 * 2 ** ((root - 69) / 12), db=loud_soft), root, 0))
        zones.append((_wav(tmp_path / f"f{root}.wav", 440 * 2 ** ((root - 69) / 12), db=-12.0), root, 1))
    return zones


def test_level_moves_smoothly_through_the_layer_switch(tmp_path):
    inst = Instrument("t", _layered(tmp_path), sustain=False)
    below = _db(inst.render(64, 1.0, 0.49, rng=random.Random(1)))
    above = _db(inst.render(64, 1.0, 0.51, rng=random.Random(1)))
    assert abs(above - below) < 1.0                       # ~20 dB without layer smoothing
    soft = _db(inst.render(64, 1.0, 0.3, rng=random.Random(1)))
    loud = _db(inst.render(64, 1.0, 0.9, rng=random.Random(1)))
    assert loud - soft > 12                               # velocity still means loudness
    # the note recorded 12 dB hot sits with its neighbours
    lv = [_db(inst.render(m, 1.0, 0.3, rng=random.Random(1))) for m in (64, 67, 72)]
    assert max(lv) - min(lv) < 2.0


def test_layer_smoothing_off_keeps_the_recorded_levels(tmp_path):
    inst = Instrument("t", _layered(tmp_path), sustain=False, smooth_layers=False)
    below = _db(inst.render(64, 1.0, 0.49, rng=random.Random(1)))
    above = _db(inst.render(64, 1.0, 0.51, rng=random.Random(1)))
    assert above - below > 15


def test_a_sharp_attack_is_not_raised_over_its_neighbours(tmp_path):
    """A pluck recorded with a quiet body but a hot attack: moving it onto its layer's level
    line would push its attack far above the others' (a pizzicato bass can hit the limiter
    that way), so that part of the correction stops 3 dB above the layer's peaks."""
    roots = list(range(40, 64, 2))
    zones = []
    for root in roots:
        for layer, db in ((0, -30.0), (1, -12.0)):
            p = _wav(tmp_path / f"{layer}_{root}.wav", 440 * 2 ** ((root - 69) / 12), db=db, seconds=1.2)
            if root == 50 and layer == 1:          # body 10 dB down, plus a full-scale click
                x, _ = sf.read(p)
                x *= 10 ** (-10 / 20)
                x[100:140] = 0.9
                sf.write(p, x, SR)
            zones.append((p, root, layer))

    def click_over_others_db(inst):
        peaks = [np.abs(inst.render(m, 0.8, 0.9, rng=random.Random(1))).max() for m in roots]
        k = roots.index(50)
        return 20 * np.log10(peaks[k] / max(peaks[:k] + peaks[k + 1:]))

    assert click_over_others_db(Instrument("t", zones, sustain=False, smooth_layers=False)) > 10
    # uncapped it would sit ~18 dB over; capped: 3 dB plus the click's own pull on the peak line
    assert click_over_others_db(Instrument("t", zones, sustain=False)) < 5.0


def test_single_layer_instruments_are_untouched(tmp_path):
    zones = [(_wav(tmp_path / f"p{r}.wav", 440 * 2 ** ((r - 69) / 12), db=-20 + r % 5), r, 0) for r in (60, 64, 67)]
    assert Instrument("t", zones).curve is None


@pytest.mark.samples
@pytest.mark.parametrize("name", ["violins", "violas", "celli", "basses", "horns",
                                  "karoryfer-bigcat-cello/01-bowed-velocity-layer", "solo_violin"])
def test_real_layers_have_no_level_jump(name):
    """Without layer smoothing these jump 11-29 dB at a layer switch, up to 15.7 dB between neighbours."""
    inst = catalog.get(name)
    lo, hi = int(inst.roots.min()), int(inst.roots.max())
    notes = list(range(lo + 2, hi - 1, max(2, (hi - lo) // 5)))
    for m in notes:
        ls = [_db(inst.render(m, 1.0, v, rng=random.Random(3)), 0.05) for v in np.arange(0.2, 0.96, 0.04)]
        assert np.abs(np.diff(ls)).max() < 8.0, (m, np.round(ls, 1))
    ls = [_db(inst.render(m, 1.0, 0.5, rng=random.Random(3)), 0.05) for m in notes]
    assert np.abs(np.diff(ls)).max() < 6.0, np.round(ls, 1)


# ---------------------------------------------------------------- 3. late bowed attacks

def _onset_ms(x, frac=0.25):
    w = int(0.01 * SR)
    e = np.sqrt(np.convolve(x.mean(axis=1) ** 2, np.ones(w) / w, mode="same"))[:int(1.5 * SR)]
    return 1000 * np.argmax(e >= np.percentile(e, 90) * frac) / SR


def test_speak_trims_a_slow_swell(tmp_path):
    zones = [(_wav(tmp_path / "bow.wav", swell=0.4), 69, 0)]
    late = Instrument("t", zones)
    early = Instrument("t", zones, speak=0.25)
    assert _onset_ms(late.render(69, 1.2, 0.7, rng=random.Random(1))) > 120
    assert _onset_ms(early.render(69, 1.2, 0.7, rng=random.Random(1))) < 25


@pytest.mark.samples
def test_solo_violin_speaks_on_time():
    """Without `speak`, notes reach -12 dB of their body after a median 80 ms (up to 420)."""
    inst = catalog.get("solo_violin")
    on = [_onset_ms(inst.render(r, 2.0, 0.3 if layer == 0 else 0.8, rng=random.Random(1)))
          for _, r, layer in inst.zones]
    assert np.median(on) < 35
    assert np.percentile(on, 90) < 90


@pytest.mark.samples
def test_clarinet_speaks_on_time():
    """Without `speak`, notes reach a quarter of their body after a median 80 ms (p90 154)."""
    inst = catalog.get("clarinet")
    on = [_onset_ms(inst.render(r, 1.0, v, rng=random.Random(1)))
          for r in sorted({int(r) for r in inst.roots}) for v in (0.4, 0.75)]
    assert np.median(on) < 35
    assert np.percentile(on, 90) < 60


# ---------------------------------------------------------------- 4. sfizz velocity curve

def test_velocity_curve_on_external_instruments(tmp_path, monkeypatch):
    note = tmp_path / "note.wav"
    _wav(note, seconds=1.5)
    monkeypatch.setattr("musicengine.external.NOTE_CACHE", tmp_path / "cache")
    monkeypatch.setattr(ExternalInstrument, "_render_to",
                        lambda self, out, *a: out.write_bytes(note.read_bytes()))
    flat = ExternalInstrument("acc", "sfizz", "x.sfz")
    curved = ExternalInstrument("acc", "sfizz", "x.sfz", velocity_curve=True)
    assert abs(_db(flat.render(60, 1.0, 0.9)) - _db(flat.render(60, 1.0, 0.3))) < 0.1
    assert _db(curved.render(60, 1.0, 0.9)) - _db(curved.render(60, 1.0, 0.3)) > 7


def test_catalog_overrides_reach_entries_and_aliases():
    assert catalog.entry("freepats-button-accordion-hn/preset-button-accordion-hn-tuned")["velocity_curve"] is True
    assert catalog.entry("solo_violin")["speak"] == 0.25
    assert catalog.entry("vcsl/idiophones-struck-idiophones-glockenspiel")["offset"] == 12


@pytest.mark.samples
def test_accordion_follows_velocity():
    inst = catalog.get("freepats-button-accordion-hn/preset-button-accordion-hn-tuned")
    assert _db(inst.render(64, 1.0, 0.85)) - _db(inst.render(64, 1.0, 0.3)) > 8


# ---------------------------------------------------------------- 5. glockenspiel pitch

@pytest.mark.samples
def test_vcsl_glockenspiel_sounds_an_octave_above_its_file_names():
    """Spectral peak of every sample = file name + 12 (the autocorrelation calibrator could
    not tell: it reads only up to 2.5 kHz)."""
    inst = catalog.get("vcsl/idiophones-struck-idiophones-glockenspiel")
    for path, root, _ in inst.zones:
        x, _ = engine.load(path)
        m = x.mean(axis=1)[int(0.02 * SR):int(0.02 * SR) + 32768]
        sp = np.abs(np.fft.rfft(m * np.hanning(len(m)), 4 * len(m)))
        fr = np.fft.rfftfreq(4 * len(m), 1 / SR)
        midi = 69 + 12 * np.log2(np.maximum(fr, 1.0) / 440)
        near = np.abs(midi - root) < 0.5
        # the root is the strongest partial, or close to it (struck bars ring upper modes)
        assert sp[near].max() > 0.5 * sp[fr > 150].max(), (path, root)
