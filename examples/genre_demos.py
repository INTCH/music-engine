"""Short demos across genres - proof that the CC0/synth catalog and the effects cover more than
orchestral music, and worked examples to copy from.

    python examples/genre_demos.py            # all demos -> out/demos/
    python examples/genre_demos.py house jazz # some of them

Each demo writes <name>.wav/.ogg/.render.json and <name>_chords.json for `musicengine analyze`.

jazz and choir use recordings only. The others pass allow_synth=True: house, lo-fi and
chiptune are synth-native styles, rock layers a synth organ, and the east-asian, indian and
middle-eastern demos use the synthesized koto, shakuhachi, sitar, oud and duduk, for which no
CC0 recording exists in the catalog.
"""
import json
import random
import sys
from pathlib import Path

from musicengine import catalog
from musicengine.score import Score, voice


OUT = Path(__file__).resolve().parent.parent / "out" / "demos"
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
      "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
QUAL = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10], "maj7": [0, 4, 7, 11],
        "5": [0, 7], "m9": [0, 3, 7, 10, 14], "sus2": [0, 2, 7], "dim": [0, 3, 6]}


def ch(name):
    """'Am7' -> (root pc, [pcs])"""
    root = name[:2] if len(name) > 1 and name[1] in "#b" else name[:1]
    q = name[len(root):]
    r = PC[root]
    return r, [(r + i) % 12 for i in QUAL[q]]


def near(pc, lo):
    return lo + ((pc - lo) % 12)


def save_chords(name, per_bar):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_chords.json").write_text(json.dumps([ch(c)[1] for c in per_bar]))


def swing(beat, amount=0.62):
    """Push off-beat eighths late (0.5 = straight, 0.667 = triplet swing)."""
    whole, frac = divmod(beat, 1.0)
    return whole + (amount if abs(frac - 0.5) < 1e-6 else frac)


# ------------------------------------------------------------------ house
def house():
    prog = ["Am", "F", "C", "G"] * 4
    s = Score(bpm=124, bars=16, seed=1, allow_synth=True)
    kick = catalog.kit("synth/drum-machine-909", "*_kick_rr*")
    clap = catalog.kit("synth/drum-machine-909", "*clap*")
    hat_c = catalog.kit("synth/drum-machine-909", "*hat-closed*")
    hat_o = catalog.kit("synth/drum-machine-909", "*hat-open*")
    s.stem("kick", level_db=-17, reverb=0.0)
    s.stem("perc", level_db=-24, reverb=0.15)
    s.stem("bass", level_db=-21, reverb=0.0, fx=[("duck", {"key": "kick", "depth_db": -6, "release": 0.18})])
    s.stem("stab", level_db=-23, reverb=0.25, fx=[("sweep", {"kind": "lp", "points": [(0, 600), (s.t(8), 6000), (s.t(16), 600)]}),
                                                   ("duck", {"key": "kick", "depth_db": -9, "release": 0.25})],
           delay=(0.75 * s.beat, 0.35, 0.25, 4000))
    s.stem("pad", level_db=-26, reverb=0.4, fx=[("duck", {"key": "kick", "depth_db": -12, "release": 0.3})])
    for b in range(16):
        r, pcs = ch(prog[b])
        for q in range(4):
            s.hit("kick", kick[q % len(kick)], b, q, 1.0)
            s.hit("perc", hat_o[b % 3], b, q + 0.5, 0.55)
            if b >= 4:
                s.hit("perc", hat_c[q % 3], b, q + 0.25, 0.25)
                s.hit("perc", hat_c[(q + 1) % 3], b, q + 0.75, 0.3)
        s.hit("perc", clap[b % 3], b, 1, 0.8)
        s.hit("perc", clap[(b + 1) % 3], b, 3, 0.8)
        for i, step in enumerate([0, 0.75, 1.5, 2.0, 2.75, 3.5]):        # acid line
            m = near(r, 33) + (12 if i in (2, 4) else 0)
            s.note("bass", "synth/acid-bass", b, step, 0.4, m, 0.6 + 0.3 * (i % 2))
        if b >= 2:
            for step in (0.5, 2.5):
                s.notes("stab", "synth/pluck-synth", b, step, 0.4, voice(pcs, 60, 76)[:3], 0.7)
        if b % 2 == 0 and b >= 8:
            s.notes("pad", "synth/supersaw", b, 0, 8, voice(pcs, 55, 72)[:4], 0.5)
    save_chords("house", prog)
    return s


# ------------------------------------------------------------------ rock
def rock():
    riff = ["E5", "E5", "G5", "A5", "E5", "E5", "C5", "D5"] * 2
    s = Score(bpm=120, bars=16, seed=2, allow_synth=True)
    s.stem("drums", level_db=-17, reverb=0.12)
    s.stem("bass", level_db=-20, reverb=0.05, fx=[("compressor", {"threshold_db": -20, "ratio": 4})])
    s.stem("gtr_l", level_db=-19, pan=-0.6, reverb=0.1, fx=[("amp", {"voicing": "crunch"})])
    s.stem("gtr_r", level_db=-19, pan=0.6, reverb=0.1, fx=[("amp", {"voicing": "crunch"})])
    s.stem("organ", level_db=-26, reverb=0.25, fx=[("leslie", {"speed": "fast"})])
    for b in range(16):
        r, _ = ch(riff[b])
        for q in range(4):
            s.note("drums", "drumkit", b, q, 0.5, 42 if b < 12 else 51, 0.6 + (0.2 if q % 2 == 0 else 0))
            s.note("drums", "drumkit", b, q + 0.5, 0.5, 42 if b < 12 else 51, 0.45)
        for k in (0, 2.5):
            s.note("drums", "drumkit", b, k, 0.5, 36, 0.95)
        for k in (1, 3):
            s.note("drums", "drumkit", b, k, 0.5, 38, 0.9)
        if b % 4 == 0:
            s.note("drums", "drumkit", b, 0, 2, 49, 0.8)
        root = near(r, 40)
        for e in range(8):
            for stem, inst in (("gtr_l", "freepats-electric-guitar-fsbs-direct/eguitarfsbs-direct-bridge-20220911"),
                               ("gtr_r", "freepats-electric-guitar-fsbs-direct/eguitarfsbs-direct-bridge-20220911")):
                s.notes(stem, inst, b, e * 0.5, 0.45, [root, root + 7, root + 12], 0.8 if e % 2 == 0 else 0.6)
            s.note("bass", "freepats-electric-bass-yr/pickedbassyr-20190930", b, e * 0.5, 0.45, near(r, 28), 0.8)
        if b >= 8 and b % 2 == 0:
            s.notes("organ", "synth/organ-rock", b, 0, 8, [root + 12, root + 19, root + 24], 0.6)
    save_chords("rock", riff)
    return s


# ------------------------------------------------------------------ jazz
def jazz():
    prog = ["Gm7", "C7", "Fmaj7", "Fmaj7", "Am7", "D7", "Gm7", "C7"] * 2
    s = Score(bpm=118, bars=16, seed=3)
    s.stem("piano", level_db=-21, reverb=0.25, pan=-0.2)
    s.stem("bass", level_db=-20, reverb=0.15, pan=0.1)
    s.stem("drums", level_db=-24, reverb=0.15)
    s.stem("sax", level_db=-19, reverb=0.3, pan=0.2)
    rng = random.Random(3)
    for b in range(16):
        r, pcs = ch(prog[b])
        third, seventh = pcs[1], pcs[3] if len(pcs) > 3 else pcs[2]
        rootless = sorted([near(third, 52), near(seventh, 52), near((r + 2) % 12, 58), near(pcs[2], 60)])
        for beat in (0.5 if b % 2 else 1.5, 3 if b % 2 else 2.5):           # syncopated comping
            s.notes("piano", "piano", b, swing(beat), 0.6, rootless, 0.45 + 0.1 * rng.random())
        nxt = ch(prog[(b + 1) % 16])[0]
        walk = [near(r, 36), near(pcs[1], 36), near(pcs[2], 36), near(nxt, 36) + rng.choice([-1, 1])]
        for q, m in enumerate(walk):
            s.note("bass", "dsmolken-double-bass/d-smolken-rubner-bass-pizz", b, q, 0.9, m, 0.7)
        for q in range(4):                                                    # ride: ding, ding-ga-ding
            s.note("drums", "drumkit", b, q, 0.5, 51, 0.55)
            if q in (1, 3):
                s.note("drums", "drumkit", b, swing(q + 0.5), 0.3, 51, 0.4)
                s.note("drums", "drumkit", b, q, 0.3, 44, 0.5)
    melody = [(0, 1.5, 74), (1.5, 0.5, 72), (2, 2, 70), (4, 3, 69), (8, 1, 67), (9, 1, 69), (10, 2, 72), (12, 4, 76),
              (16, 1.5, 77), (17.5, 0.5, 76), (18, 2, 74), (20, 2, 72), (24, 1, 70), (25, 1, 72), (26, 2, 74), (28, 4, 69)]
    for start in (16, 48):
        for beat, beats, m in melody:
            s.note("sax", "vcsl/aerophones-reed-aerophones-tenor-saxophone-vibrato", 0, (start + swing(beat)), beats, m - 12, 0.7)
    save_chords("jazz", prog)
    return s


# ------------------------------------------------------------------ lo-fi
def lofi():
    prog = ["Fmaj7", "Em7", "Dm7", "Cmaj7"] * 3
    s = Score(bpm=80, bars=12, seed=4, allow_synth=True)
    kick = catalog.kit("synth/drum-machine-808", "*_kick_rr*")
    snare = catalog.kit("synth/drum-machine-808", "*snare*")
    hat = catalog.kit("synth/drum-machine-808", "*hat-closed*")
    s.stem("keys", level_db=-20, reverb=0.3, fx=[("tape", {"saturation": 2.0, "tone": 6000}), ("eq", [("lp", 5000)])])
    s.stem("drums", level_db=-19, reverb=0.1, fx=[("bitcrush", {"bits": 12}), ("eq", [("lp", 7000)])])
    s.stem("bass", level_db=-21, reverb=0.0)
    for b in range(12):
        r, pcs = ch(prog[b])
        s.notes("keys", "synth/e-piano", b, 0, 2.2, voice(pcs, 55, 72)[:4], 0.5)
        s.notes("keys", "synth/e-piano", b, swing(2.5, 0.6), 1.3, voice(pcs, 55, 72)[1:4], 0.38)
        s.hit("drums", kick[0], b, 0, 0.9)
        s.hit("drums", kick[1], b, swing(2.5, 0.6), 0.7)
        s.hit("drums", snare[0], b, 1, 0.6)
        s.hit("drums", snare[1], b, 3, 0.6)
        for e in range(8):
            s.hit("drums", hat[e % 3], b, swing(e * 0.5, 0.6), 0.25 if e % 2 else 0.35)
        s.note("bass", "synth/sub-bass", b, 0, 2.5, near(r, 33), 0.7)
        s.note("bass", "synth/sub-bass", b, swing(2.5, 0.6), 1.2, near(r, 33), 0.6)
    save_chords("lofi", prog)
    return s


# ------------------------------------------------------------------ east asian (koto, shakuhachi, taiko)
def east_asian():
    scale = [62, 64, 65, 69, 70, 74, 76, 77, 81]          # D in-scale (miyako-bushi): D E F A Bb
    s = Score(bpm=72, bars=12, seed=5, allow_synth=True)
    taiko = catalog.kit("vcsl/membranophones-struck-membranophones-bass-drum-1")
    s.stem("koto", level_db=-20, reverb=0.35, pan=-0.2)
    s.stem("flute", level_db=-19, reverb=0.45, pan=0.15)
    s.stem("taiko", level_db=-24, reverb=0.3, fx=[("compressor", {"threshold_db": -24, "ratio": 3, "attack": 0.003})])
    rng = random.Random(5)
    for b in range(12):
        for i in range(8):
            if i in (0, 3, 5) or rng.random() < 0.25:
                s.note("koto", "synth/koto", b, i * 0.5, 1.0, scale[(i * 2 + b) % 5], 0.55 + 0.2 * (i == 0))
        s.hit("taiko", taiko[b % len(taiko)], b, 0, 0.9)
        if b % 2 == 1:
            s.hit("taiko", taiko[(b + 1) % len(taiko)], b, 2.5, 0.6)
            s.hit("taiko", taiko[(b + 2) % len(taiko)], b, 3, 0.75)
    phrase = [(0, 3, 74), (3, 1, 76), (4, 4, 77), (8, 2, 76), (10, 2, 74), (12, 4, 69),
              (16, 3, 70), (19, 1, 69), (20, 4, 65), (24, 6, 62)]
    for start in (8, 24):
        for beat, beats, m in phrase:
            if start + beat < 48:
                s.note("flute", "synth/shakuhachi", 0, start + beat, beats * 0.95, m, 0.7)
    save_chords("east_asian", ["Dm"] * 12)
    return s


# ------------------------------------------------------------------ indian (sitar, tabla, drone)
def indian():
    s = Score(bpm=90, bars=12, seed=6, allow_synth=True)
    tabla = {Path(p).stem: p for p in catalog.kit("sonicpi/tabla")}
    names = sorted(tabla)
    s.stem("drone", level_db=-25, reverb=0.4, width=1.3)
    s.stem("sitar", level_db=-18, reverb=0.3, pan=0.1)
    s.stem("tabla", level_db=-23, reverb=0.2, pan=-0.1, fx=[("compressor", {"threshold_db": -24, "ratio": 3, "attack": 0.003})])
    for b in range(12):                                      # tanpura-like drone: Pa Sa Sa Sa
        for i, m in enumerate([45, 50, 50, 38]):
            s.note("drone", "synth/sitar", b, i, 1.8, m, 0.35)
    raga = [62, 63, 66, 67, 69, 70, 73, 74]                 # D bhairav-ish: D Eb F# G A Bb C# D
    line = [(0, 1, 0), (1, 0.5, 1), (1.5, 0.5, 2), (2, 2, 3), (4, 1, 4), (5, 1, 3), (6, 2, 2),
            (8, 0.5, 4), (8.5, 0.5, 5), (9, 1, 7), (10, 2, 6), (12, 1, 5), (13, 1, 4), (14, 2, 3)]
    for start in (8, 24):
        for beat, beats, k in line:
            s.note("sitar", "synth/sitar", 0, start + beat, beats, raga[k], 0.7)
    teental = ["tabla_dhec", "tabla_ghe1", "tabla_na", "tabla_tas1", "tabla_ghe2", "tabla_na_o", "tabla_re", "tabla_te1"]
    pick = [n for n in teental if n in tabla] or names
    for b in range(4, 12):
        for i in range(8):
            s.hit("tabla", tabla[pick[(i + b) % len(pick)]], b, i * 0.5, 0.8 if i % 4 == 0 else 0.55)
    save_chords("indian", ["D"] * 12)
    return s


# ------------------------------------------------------------------ middle eastern (oud, duduk, darbuka)
def middle_eastern():
    hijaz = [62, 63, 66, 67, 69, 70, 72, 74]                 # D hijaz: D Eb F# G A Bb C D
    s = Score(bpm=96, bars=12, seed=7, allow_synth=True)
    s.stem("oud", level_db=-19, reverb=0.25, pan=-0.25)
    s.stem("duduk", level_db=-19, reverb=0.4, pan=0.2)
    s.stem("perc", level_db=-20, reverb=0.15)
    maqsum = [(0, 69), (0.5, 70), (1.5, 70), (2, 69), (3, 70), (3.5, 71)]   # doum tak - tak doum - tak tak
    for b in range(12):
        for beat, key in maqsum:
            s.note("perc", "world_perc", b, beat, 0.4, key, 0.8 if key == 69 else 0.6)
        for i, k in enumerate([0, 1, 2, 1, 0, 1, 2, 3]):
            s.note("oud", "synth/oud", b, i * 0.5, 0.6, hijaz[k] - 12, 0.6 if i % 2 else 0.75)
    phrase = [(0, 2, 4), (2, 1, 5), (3, 1, 4), (4, 4, 2), (8, 1, 1), (9, 1, 2), (10, 2, 3), (12, 4, 0)]
    for start in (16, 32):
        for beat, beats, k in phrase:
            s.note("duduk", "synth/duduk", 0, start + beat, beats, hijaz[k], 0.7)
    save_chords("middle_eastern", ["D"] * 12)
    return s


# ------------------------------------------------------------------ chiptune
def chiptune():
    prog = ["C", "Am", "F", "G"] * 4
    s = Score(bpm=150, bars=16, seed=8, allow_synth=True)
    hat = catalog.kit("synth/drum-machine-808", "*maracas*")
    snare = catalog.kit("synth/drum-machine-808", "*snare*")
    kick = catalog.kit("synth/drum-machine-808", "*_kick_rr*")
    s.stem("lead", level_db=-19, reverb=0.05)
    s.stem("arp", level_db=-24, reverb=0.05, pan=0.3)
    s.stem("bass", level_db=-20, reverb=0.0)
    s.stem("drums", level_db=-22, reverb=0.0, fx=[("bitcrush", {"bits": 6, "downsample": 2})])
    melody = [76, 79, 84, 83, 81, 79, 76, 74, 72, 74, 76, 79, 77, 76, 74, 71]
    for b in range(16):
        r, pcs = ch(prog[b])
        tones = voice(pcs, 72, 88)
        for i in range(16):
            s.note("arp", "synth/chip-pulse", b, i * 0.25, 0.2, tones[i % len(tones)], 0.5)
        for q in range(4):
            s.note("bass", "synth/chip-triangle", b, q, 0.45, near(r, 36), 0.8)
            s.note("bass", "synth/chip-triangle", b, q + 0.5, 0.45, near(r, 36) + 12, 0.7)
            s.hit("drums", hat[q % 3], b, q + 0.5, 0.5)
        s.hit("drums", kick[0], b, 0, 0.9)
        s.hit("drums", snare[0], b, 2, 0.8)
        if b >= 4:
            for k in range(2):
                m = melody[((b - 4) * 2 + k) % len(melody)]
                s.note("lead", "synth/chip-square", b, k * 2, 1.9, m, 0.7)
    save_chords("chiptune", prog)
    return s


# ------------------------------------------------------------------ choir
def choir():
    prog = ["D", "Bm", "G", "A", "D", "Bm", "Em", "A"]
    s = Score(bpm=66, bars=8, seed=9, loop=False)
    s.stem("choir", level_db=-19, reverb=0.6, width=1.2)
    s.stem("organ", level_db=-27, reverb=0.5)
    sop = [74, 74, 74, 73, 74, 74, 71, 73]
    for b in range(8):
        r, pcs = ch(prog[b])
        bass_n = near(r, 40)
        ten = voice(pcs, 52, 60)[0]
        alt = voice(pcs, 60, 67)[-1]
        for m in (bass_n, ten, alt, sop[b]):
            s.note("choir", "choir", b, 0, 4.05, m, 0.6)
        s.notes("organ", "organ_quiet", b, 0, 4, [bass_n - 12, bass_n], 0.4)
    save_chords("choir", prog)
    return s


DEMOS = {"house": house, "rock": rock, "jazz": jazz, "lofi": lofi, "east_asian": east_asian, "indian": indian,
         "middle_eastern": middle_eastern, "chiptune": chiptune, "choir": choir}

if __name__ == "__main__":
    names = sys.argv[1:] or list(DEMOS)
    for n in names:
        s = DEMOS[n]()
        out, levels, gr = s.render(str(OUT / n), ir_seconds=3.5, stems=(n == "house"), midi=True)
        print(f"{n:15s} {len(out) / 48000:5.1f}s  limiter GR {gr * 100:4.1f}%")
