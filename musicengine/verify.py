"""Measure a render against its plan.json in one go. An automated composer (such as an AI coding
agent) cannot listen, so this is the gate a render passes before anyone hears it.

    python -m musicengine verify plan.json out/track.wav       # exit 1 when anything FAILs

Checks (FAIL blocks showing the render, WARN needs a look, INFO is context):
- licenses / recordings only (render.json)                         FAIL
- clipping                                                         FAIL
- length matches the plan's bars                                   FAIL
- loop seam                                                        FAIL
- loudness on target, true peak under the ceiling (wav and ogg)    FAIL / WARN for ogg
- limiter working hard                                             WARN
- chroma agreement with the planned chords                         WARN (overtones lower it; a lead, not proof)
- section levels follow the planned dynamics                       WARN
- the reference track's tempo, loudness and balance                INFO
Writes <out_base>.verify.json next to the render.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from . import analyze, loudness, plan as planmod
from .plan import DYNAMICS

ALLOWED = {"CC0-1.0", "Unlicense", "Public-Domain"}


def _spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def license_check(side, synth_reason=None):
    """(status, check, detail) for render.json. Synthesized sound passes only when the plan says why."""
    bad = sorted(set(side.get("licenses", [])) - ALLOWED - ({"Synthesized"} if synth_reason else set()))
    if bad or not (side.get("recorded_only", False) or synth_reason):
        return ("FAIL", "licenses", f"licenses {side.get('licenses')}, recorded_only={side.get('recorded_only')}, "
                                    f"synthetic={side.get('synthetic')}")
    if side.get("recorded_only", False):
        return ("PASS", "licenses", ", ".join(side["licenses"]) + ", recordings only")
    return ("PASS", "licenses", ", ".join(side["licenses"]) + f"; synthesized sound, as planned: {synth_reason}")


def verify(plan_path, wav):
    p = planmod.load(plan_path)
    g = p["global"]
    base = str(Path(wav).with_suffix(""))
    rows = []

    def add(status, check, detail):
        rows.append(dict(status=status, check=check, detail=detail))

    side = None
    try:
        with open(base + ".render.json", encoding="utf-8") as fh:
            side = json.load(fh)
    except FileNotFoundError:
        add("FAIL", "render.json", f"{base}.render.json missing: render with Score.render")

    if side:
        add(*license_check(side, p.get("synth")))

    x, sr = sf.read(wav, dtype="float32", always_2d=True)
    bar_s = 60 / g["bpm"] * g["beats_per_bar"]
    expect_s = g["bars"] * bar_s
    secs = len(x) / sr
    if g["loop"]:
        ok = abs(secs - expect_s) < 0.01
        add("PASS" if ok else "FAIL", "length", f"{secs:.2f}s, plan {expect_s:.2f}s (loop)")
    else:
        ok = secs >= expect_s - 0.01
        add("PASS" if ok else "FAIL", "length", f"{secs:.2f}s, plan {expect_s:.2f}s + tail (one-shot)")

    lines = []
    res = analyze.run(wav, g["bpm"], g["beats_per_bar"], planmod.chords(p), png=True, out=lines.append)
    add("PASS" if res["clipped"] == 0 else "FAIL", "clipping", f"{res['clipped']} clipped samples")
    if g["loop"]:
        sm = res["seam"]
        add("PASS" if sm["ok"] else "FAIL", "loop seam",
            f"step {sm['jump']:.4f} vs {sm['near']:.4f} nearby; edge levels {sm['tail_db']:.1f}/{sm['head_db']:.1f} dB")

    lv = side.get("loudness") if side else None
    lv = lv or loudness.measure(x)
    master = (side or {}).get("master", {})
    if "target_lufs" in master:
        tgt, ceil = master["target_lufs"], master["ceiling_dbtp"]
        add("PASS" if abs(lv["lufs"] - tgt) <= 1.0 else "FAIL", "loudness", f"{lv['lufs']} LUFS, target {tgt}")
        add("PASS" if lv["true_peak_db"] <= ceil + 0.1 else "FAIL", "true peak", f"{lv['true_peak_db']} dBTP, ceiling {ceil}")
        if lv.get("ogg_true_peak_db") is not None:
            add("PASS" if lv["ogg_true_peak_db"] <= ceil + 0.5 else "WARN", "ogg true peak",
                f"{lv['ogg_true_peak_db']} dBTP after Vorbis encoding")
        lim = master.get("limiter_max_gr_db", 0)
        add("PASS" if lim <= 3.0 else "WARN", "limiter", f"max {lim} dB gain reduction"
            + ("" if lim <= 3.0 else ": lower or compress the loudest stem (usually drums)"))
        add("INFO", "dynamics", f"LRA {lv['lra']} LU, PLR {lv['plr']} dB, glue {master.get('glue_max_gr_db')} dB")
    else:
        add("INFO", "loudness", f"{lv['lufs']} LUFS, {lv['true_peak_db']} dBTP (no master settings in render.json: no target)")

    ca = res.get("chroma_agreement")
    cmin = p.get("verify", {}).get("chroma_min", 0.8)
    if ca is not None:
        worst = [b for b, good in enumerate(res["chroma_bars"]) if good is not None and good <= 1]
        add("PASS" if ca >= cmin else "WARN", "chroma vs chords",
            f"{ca:.0%} (min {cmin:.0%})" + (f"; weakest bars (0-based) {worst[:12]}" if worst else ""))

    # section level vs planned dynamic
    levels, marks = [], []
    for s in p["sections"]:
        a, b = s["bars"]
        seg = [v for v in res["bar_db"][a:b]]
        if seg:
            levels.append(float(np.mean(seg)))
            marks.append(DYNAMICS.index(s["dynamic"]))
    rho_min = p.get("verify", {}).get("dynamics_min_rho", 0.6)
    if len(levels) >= 3 and len(set(marks)) > 1:
        rho = _spearman(marks, levels)
        detail = ", ".join(f"{s['name']} {s['dynamic']} {lv_:.1f} dB" for s, lv_ in zip(p["sections"], levels))
        add("PASS" if rho is not None and rho >= rho_min else "WARN", "dynamics arc",
            f"rank correlation {rho:.2f} (min {rho_min}): {detail}" if rho is not None else detail)
    if g["loop"] and len(levels) >= 2:
        d = abs(levels[0] - levels[-1])
        add("PASS" if d <= 6 else "WARN", "loop energy", f"first/last section differ by {d:.1f} dB")

    if p.get("reference"):
        from .reference import compare
        try:
            c = compare(wav, str(Path(p["_path"]).parent / p["reference"]) if not Path(p["reference"]).is_absolute()
                        else p["reference"])
            keep = {"tempo bpm", "integrated LUFS", "tilt dB/oct", "centroid Hz", "onsets/s", "side/mid dB"}
            add("INFO", "reference", "; ".join(f"{n} {d:+g}" for n, _, _, d in c["rows"] if n in keep))
        except FileNotFoundError as e:
            add("WARN", "reference", f"not found: {e.filename}")

    status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else \
        "WARN" if any(r["status"] == "WARN" for r in rows) else "PASS"
    report = dict(plan=plan_path, render=wav, status=status, checks=rows, analysis=lines)
    with open(base + ".verify.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    return report


def main(argv):
    r = verify(argv[0], argv[1])
    for row in r["checks"]:
        print(f"{row['status']:4s}  {row['check']:18s} {row['detail']}")
    print(f"=> {r['status']}  ({Path(r['render']).with_suffix('')}.verify.json)")
    sys.exit(1 if r["status"] == "FAIL" else 0)
