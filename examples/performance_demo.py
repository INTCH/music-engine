"""The same melody twice: placed note by note (plain) and played as a line (performed:
legato, swells on long notes, phrase shaping). Everything else - pad, seed, master - is
identical, so the difference is the performance layer alone.

    python -I examples/performance_demo.py      # -> out/perform/{plain,performed}.wav + numbers

A cello states an 8-bar phrase in D minor, a solo violin answers an octave up; violas and
basses hold the chords quietly underneath. 72 bpm, one-shot.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from musicengine.score import Score

OUT = Path(__file__).resolve().parent.parent / "out" / "perform"
BPM = 72
PCS = {"Dm": [2, 5, 9], "Bb": [10, 2, 5], "Gm": [7, 10, 2], "A": [9, 1, 4], "F": [5, 9, 0], "C": [0, 4, 7]}
CHORDS = ["Dm", "Bb", "Gm", "A", "Dm", "F", "Gm", "A", "F", "C", "Dm", "Bb", "Gm", "Dm", "A", "Dm"]
ROOT = {"Dm": 38, "Bb": 34, "Gm": 43, "A": 33, "F": 41, "C": 36}
PAD = {"Dm": [57, 62], "Bb": [58, 62], "Gm": [58, 62], "A": [57, 61], "F": [57, 60], "C": [55, 60]}

# (bar, beat, beats, midi, vel)
CELLO = [(0, 0, 2, 57, .55), (0, 2, 1, 62, .55), (0, 3, 1, 64, .55), (1, 0, 3, 65, .6), (1, 3, 1, 64, .55),
         (2, 0, 2, 62, .55), (2, 2, 1, 58, .5), (2, 3, 1, 60, .5), (3, 0, 4, 57, .5),
         (4, 1, 1, 62, .55), (4, 2, 1, 65, .58), (4, 3, 1, 69, .6), (5, 0, 2, 69, .65), (5, 2, 1, 67, .6),
         (5, 3, 1, 65, .58), (6, 0, 2, 67, .6), (6, 2, 1, 65, .55), (6, 3, 1, 64, .55), (7, 0, 2, 64, .5),
         (7, 2, 2, 61, .5)]
VIOLIN = [(8, 0, 2, 69, .5), (8, 2, 1, 72, .55), (8, 3, 1, 74, .55), (9, 0, 3, 76, .6), (9, 3, 1, 74, .55),
          (10, 0, 2, 77, .62), (10, 2, 1, 76, .58), (10, 3, 1, 74, .55), (11, 0, 4, 74, .5),
          (12, 1, 1, 70, .55), (12, 2, 1, 74, .58), (12, 3, 1, 79, .62), (13, 0, 2, 77, .62), (13, 2, 1, 76, .58),
          (13, 3, 1, 74, .55), (14, 0, 2, 73, .55), (14, 2, 2, 76, .55), (15, 0, 4, 74, .5)]


def build(performed):
    s = Score(bpm=BPM, bars=16, seed=7, loop=False, tail=6.0, genre="orchestral")
    s.stem("melody", level_db=-19, reverb=0.4)
    s.stem("pad", level_db=-27, reverb=0.5, width=1.2)
    s.stem("bass", level_db=-26, reverb=0.35)
    for b, ch in enumerate(CHORDS):
        s.notes("pad", "violas", b, 0, 4, PAD[ch], vel=0.4)
        s.note("bass", "basses", b, 0, 4, ROOT[ch], vel=0.45)
    for inst, notes in (("celli", CELLO), ("solo_violin", VIOLIN)):
        if performed:
            s.line("melody", inst, notes)
        else:
            for n in notes:
                s.note("melody", inst, *n)
    return s


def transitions(stem_wav, notes):
    """How continuous the line is at each note change that follows a note (not a rest): the
    level of the first 150 ms after the onset against the level around it. 0 dB = seamless;
    positive = a hole (slow attack after a released note); negative = a bump (re-articulation).
    Recorded sustains wobble by a few dB on their own, so only the mean is meaningful."""
    x, sr = sf.read(stem_wav, dtype="float32")
    m = x.mean(axis=1)
    beat = 60 / BPM

    def lev(a, b):
        s = m[max(0, a):b]
        return 10 * np.log10((s ** 2).mean() + 1e-12)
    holes = []
    for i, (bar, bt, beats, midi, vel) in enumerate(notes[1:], 1):
        pb = notes[i - 1]
        if (bar * 4 + bt) - (pb[0] * 4 + pb[1] + pb[2]) > 0.01:
            continue                                     # after a rest: an attack is right
        c = int((bar * 4 + bt) * beat * sr)
        around = 0.5 * lev(c - int(0.4 * sr), c - int(0.1 * sr)) + 0.5 * lev(c + int(0.25 * sr), c + int(0.55 * sr))
        holes.append(around - lev(c, c + int(0.15 * sr)))
    return dict(joined=len(holes), mean_abs_db=round(float(np.mean(np.abs(holes))), 2),
                mean_db=round(float(np.mean(holes)), 2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, perf in (("plain", False), ("performed", True)):
        s = build(perf)
        base = str(OUT / name)
        s.render(base, ir_seconds=4.5, stems=True)
        stem = f"{base}_stems/melody.wav"
        report[name] = dict(loudness=json.load(open(base + ".render.json"))["loudness"],
                            cello=transitions(stem, CELLO), violin=transitions(stem, VIOLIN))
        json.dump([PCS[c] for c in CHORDS], open(base + "_chords.json", "w"))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    sys.exit(main())
