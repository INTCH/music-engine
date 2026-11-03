"""plan.json: validation, chord reading, Score setup, summary."""
import copy
import json
from pathlib import Path

import pytest

from musicengine import plan

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "plans" / "war_theme.plan.json"


def _example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_plan_is_valid():
    assert plan.validate(_example()) == []


@pytest.mark.parametrize("sym,pcs", [("Dm", [2, 5, 9]), ("Bb", [10, 2, 5]), ("F#m7b5", [6, 9, 0, 4]),
                                     ("Asus4", [9, 2, 4]), ("C/E", [0, 4, 7]), ("C/D", [0, 4, 7, 2]),
                                     ("Ebmaj7", [3, 7, 10, 2]), ([2, 5, 9], [2, 5, 9]),
                                     ("D6/9", [2, 6, 9, 11, 4]), ("Em6/9", [4, 7, 11, 1, 6]),
                                     ("C6/9/E", [0, 4, 7, 9, 2]), ("E/D", [4, 8, 11, 2]),
                                     ("C/G", [0, 4, 7])])
def test_chords(sym, pcs):
    assert plan.chord_pcs(sym) == pcs


def test_no_chord_and_bad_chord():
    assert plan.chord_pcs("N") is None
    with pytest.raises(plan.PlanError):
        plan.chord_pcs("Hm")
    with pytest.raises(plan.PlanError):
        plan.chord_pcs("C/9")


def test_chords_per_bar_cycles_short_lists():
    p = _example()
    p["sections"][0]["chords"] = ["Dm", "A"]
    per_bar = plan.chords(p)
    assert len(per_bar) == 48
    assert per_bar[:4] == [[2, 5, 9], [9, 1, 4], [2, 5, 9], [9, 1, 4]]


@pytest.mark.parametrize("mutate,expect", [
    (lambda p: p["sections"][1].__setitem__("bars", [9, 16]), "previous section ended"),
    (lambda p: p["global"].__setitem__("bars", 40), "global.bars"),
    (lambda p: p["sections"][0].__setitem__("dynamic", "loud"), "dynamic"),
    (lambda p: p.__setitem__("rationale", []), "rationale"),
    (lambda p: p["global"].__setitem__("genre", "polka"), "genre"),
    (lambda p: p.pop("motif"), "motif"),
    (lambda p: p.__setitem__("use", "background"), "use"),
    (lambda p: p.__setitem__("synth", ""), "synth"),
])
def test_validation_catches(mutate, expect):
    p = copy.deepcopy(_example())
    mutate(p)
    errs = plan.validate(p)
    assert any(expect in e for e in errs), errs


def test_score_from_plan():
    p = _example()
    s = plan.score(p, seed=7)
    assert s.bars == 48 and s.bpb == 4 and s.loop and s.genre == "cinematic"
    assert abs(60 / s.beat - 112) < 1e-9
    assert not s.allow_synth


def test_synth_only_with_a_reason():
    p = _example()
    p["synth"] = "synthwave: the genre is built on synths"
    assert plan.validate(p) == []
    assert plan.score(p).allow_synth
    assert "Synthesized sound: synthwave" in plan.summary(p)


@pytest.mark.parametrize("planned,recorded_only,status", [(None, True, "PASS"), (None, False, "FAIL"),
                                                          ("chiptune", False, "PASS")])
def test_verify_synth_gate(planned, recorded_only, status):
    from musicengine import verify
    side = dict(licenses=["CC0-1.0"] + ([] if recorded_only else ["Synthesized"]), recorded_only=recorded_only,
                synthetic={} if recorded_only else {"synth/saw-lead": "x"})
    assert verify.license_check(side, planned)[0] == status
    side["licenses"].append("CC-BY-4.0")
    assert verify.license_check(side, planned)[0] == "FAIL"


def test_summary_mentions_every_section():
    text = plan.summary(_example())
    for name in ("Breakdown", "Peak", "D minor", "Why:"):
        assert name in text
