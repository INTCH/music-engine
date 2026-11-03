"""Command line.

  python -m musicengine search cello                # find instruments (name/path/family words)
  python -m musicengine search --family drums snare
  python -m musicengine info vsco/strings-cello-section-susvib
  python -m musicengine fetch violins horns         # download + calibrate now
  python -m musicengine check violins               # render notes across the range, measure pitch
  python -m musicengine analyze track.wav 72 4 [chords.json]
  python -m musicengine hiss track.wav
  python -m musicengine credits track.render.json   # sources a render used, from its sidecar
  python -m musicengine reference song.mp3 [out.json]   # measure a reference track (local file)
  python -m musicengine compare track.wav song.reference.json
  python -m musicengine loudness track.wav               # LUFS, LRA, true peak, PLR
  python -m musicengine plan check|summary plan.json
  python -m musicengine verify plan.json track.wav        # every check against the plan
"""
import json
import runpy
import sys

import numpy as np


def _check(name):
    from . import catalog
    from .calibrate import detect_midi
    from .engine import write
    import os
    import random
    import tempfile
    inst = catalog.get(name)
    lo, hi = (int(inst.roots.min()), int(inst.roots.max())) if hasattr(inst, "roots") else (48, 84)
    bad = 0
    for m in range(lo + 2, hi, max(1, (hi - lo) // 6)):
        x = inst.render(m, 1.5, 0.7, rng=random.Random(1))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "n.wav")
            write(p, x / (np.abs(x).max() + 1e-9) * 0.5)
            d = detect_midi(p)
        off = d - m
        oct_ok = abs(off - 12 * round(off / 12)) < 0.6
        ok = abs(off) < 0.6
        bad += not ok
        print(f"  midi {m:3d} -> measured {d:6.2f}  {'OK' if ok else ('OCTAVE?' if oct_ok else 'WRONG')}")
    print(f"{name}: {'all notes on pitch' if not bad else f'{bad} notes off (octave errors of the detector are common on low/percussive notes)'}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    from . import catalog
    if cmd == "search":
        fam = None
        if rest[:1] == ["--family"]:
            fam, rest = rest[1], rest[2:]
        names = catalog.search(" ".join(rest), family=fam)
        print("\n".join(names) or "(nothing)")
        print(f"-- {len(names)} match(es)")
    elif cmd == "info":
        for n in rest:
            e = catalog.entry(n)
            lic, credit = catalog.license_of(e)
            print(json.dumps(dict(e, license=lic, credit=credit), indent=1, ensure_ascii=False))
    elif cmd == "fetch":
        for n in rest:
            e = catalog.entry(n)
            catalog.kit(n) if e["rule"] == "kit" else catalog.get(n)
            print(f"{n}: ready")
    elif cmd == "check":
        for n in rest:
            _check(n)
    elif cmd in ("analyze", "hiss"):
        sys.argv = [cmd] + rest
        runpy.run_module(f"musicengine.{cmd}", run_name="__main__")
    elif cmd == "reference":
        from .reference import main as ref_main
        ref_main(rest)
    elif cmd == "compare":
        from .reference import main as ref_main
        ref_main(["compare"] + rest)
    elif cmd == "plan":
        from .plan import main as plan_main
        plan_main(rest)
    elif cmd == "verify":
        from .verify import main as verify_main
        verify_main(rest)
    elif cmd == "loudness":
        from .loudness import measure
        from .reference import load
        for p in rest:
            print(json.dumps(dict(file=p, **measure(load(p)))))
    elif cmd == "credits":
        for p in rest:
            print("\n".join(json.load(open(p, encoding="utf-8"))["credits"]))
    else:
        print(f"unknown command {cmd}\n{__doc__}")
        sys.exit(2)


def run():
    """Entry point of the `musicengine` console script (same as python -m musicengine)."""
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
