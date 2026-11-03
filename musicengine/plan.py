"""plan.json: the whole piece decided before any note is written, in a form the engine can
read and check. The track script builds its Score from it, verify measures the render against
it, and summary turns it into a short text for a human to approve.

    python -m musicengine plan check plan.json        # validate
    python -m musicengine plan summary plan.json      # readable summary for approval
    python -m musicengine verify plan.json out/track.wav

    from musicengine import plan
    p = plan.load("plan.json")
    s = plan.score(p, seed=1)                 # Score with bpm, bars, meter, loop, genre, reference
    for bar, pcs in enumerate(plan.chords(p)): ...

Shape (keys marked ? are optional):

{
  "schema": "musicengine.plan/1",
  "title": "Banners Raised",
  "use": "loop" | "cue" | "stinger" | "song" | "stems",
  "brief": "what was asked, in one or two sentences",
  "reference"?: "path/to/song.reference.json",
  "synth"?: "why synthesized sound belongs in this piece (synth genre, or asked for)",
  "global": {"bpm": 112, "beats_per_bar": 4, "key": "D", "mode": "minor", "bars": 48,
             "loop": true, "genre"?: "cinematic", "target_lufs"?: -16},
  "sections": [
    {"name": "A", "function": "intro|A|B|build|peak|breakdown|outro|...", "bars": [0, 8],
     "chords": ["Dm", "Bb", "C", "Dm", "Gm", "Bb", "C", "A"],     # one per bar, or a cycle
     "dynamic": "pp|p|mp|mf|f|ff",
     "instruments": [{"name": "celli_spic", "role": "rhythm", "stem": "ostinato"}]}
  ],
  "motif": {"notes": [[62, 1.0], [65, 0.5], [69, 2.5]], "description": "rising minor sixth"},
  "mix"?: {"stems": {"ostinato": {"level_db": -21, "reverb": 0.32, "role"?: "drums"}}},
  "rationale": [{"decision": "D minor, 112 bpm", "why": "...", "source": "docs/agents/brief.md#mood-to-music"}],
  "verify"?: {"chroma_min": 0.8, "dynamics_min_rho": 0.6}
}

Chord symbols: root (C, C#, Db...) + quality: "" m 5 7 maj7 m7 m7b5 dim dim7 aug sus2 sus4 add9
6 m6 6/9 m6/9 9 m9 maj9 7sus4; a slash bass ("C/E") adds the bass note. "N" means no chord (not checked).
Or give the pitch classes directly: [2, 5, 9].
"""
import json
import re

SCHEMA = "musicengine.plan/1"
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
      "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11, "E#": 5, "Fb": 4, "B#": 0}
QUALITY = {"": [0, 4, 7], "m": [0, 3, 7], "5": [0, 7], "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11],
           "m7": [0, 3, 7, 10], "m7b5": [0, 3, 6, 10], "dim": [0, 3, 6], "dim7": [0, 3, 6, 9],
           "aug": [0, 4, 8], "sus2": [0, 2, 7], "sus4": [0, 5, 7], "sus": [0, 5, 7], "add9": [0, 4, 7, 2],
           "madd9": [0, 3, 7, 2], "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9], "9": [0, 4, 7, 10, 2],
           "m9": [0, 3, 7, 10, 2], "maj9": [0, 4, 7, 11, 2], "7sus4": [0, 5, 7, 10], "6/9": [0, 4, 7, 9, 2],
           "m6/9": [0, 3, 7, 9, 2]}
DYNAMICS = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
USES = {"loop", "cue", "stinger", "song", "stems"}
# "/9" belongs to the quality (6/9); any other slash names the bass ("C/E", "D6/9/F#")
_CHORD = re.compile(r"^([A-G][#b]?)([^/]*(?:/9)?)(?:/([A-G][#b]?))?$")


class PlanError(ValueError):
    pass


def chord_pcs(sym):
    """'Dm' -> [2, 5, 9]; 'C/E' -> [0, 4, 7] (E already in it); 'N' -> None; [2, 5, 9] passes."""
    if isinstance(sym, list):
        return [int(p) % 12 for p in sym]
    if sym in ("N", "N.C.", "-"):
        return None
    m = _CHORD.match(sym.strip())
    if not m or m.group(2) not in QUALITY:
        raise PlanError(f"cannot read chord {sym!r}; qualities: {sorted(QUALITY)}")
    r = PC[m.group(1)]
    pcs = [(r + i) % 12 for i in QUALITY[m.group(2)]]
    if m.group(3):
        b = PC[m.group(3)]
        if b not in pcs:
            pcs.append(b)
    return pcs


def validate(p):
    """-> list of problems (empty when the plan is usable)."""
    errs = []

    def need(obj, key, kind, where):
        if key not in obj:
            errs.append(f"{where}: missing {key!r}")
            return False
        if not isinstance(obj[key], kind):
            errs.append(f"{where}.{key}: expected {kind if isinstance(kind, type) else kind[0]}")
            return False
        return True

    if p.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}")
    need(p, "title", str, "plan")
    if need(p, "use", str, "plan") and p["use"] not in USES:
        errs.append(f"plan.use: one of {sorted(USES)}")
    need(p, "brief", str, "plan")
    if need(p, "global", dict, "plan"):
        g = p["global"]
        for k, kind in (("bpm", (int, float)), ("beats_per_bar", int), ("key", str), ("mode", str), ("bars", int),
                        ("loop", bool)):
            need(g, k, kind, "global")
        if isinstance(g.get("key"), str) and g["key"] not in PC:
            errs.append(f"global.key: {g['key']!r} is not a note name")
        if g.get("genre") is not None:
            from .mastering import preset
            try:
                preset(g["genre"])
            except ValueError as e:
                errs.append(f"global.genre: {e}")
    if need(p, "sections", list, "plan"):
        prev_end = 0
        for i, s in enumerate(p["sections"]):
            w = f"sections[{i}]"
            if not isinstance(s, dict):
                errs.append(f"{w}: expected an object")
                continue
            need(s, "name", str, w)
            need(s, "function", str, w)
            if need(s, "bars", list, w):
                if len(s["bars"]) != 2 or not all(isinstance(b, int) for b in s["bars"]) or s["bars"][1] <= s["bars"][0]:
                    errs.append(f"{w}.bars: [start, end) with end > start")
                elif s["bars"][0] != prev_end:
                    errs.append(f"{w}.bars: starts at {s['bars'][0]}, previous section ended at {prev_end}")
                else:
                    prev_end = s["bars"][1]
            if need(s, "chords", list, w):
                if not s["chords"]:
                    errs.append(f"{w}.chords: empty")
                for c in s["chords"]:
                    try:
                        chord_pcs(c)
                    except PlanError as e:
                        errs.append(f"{w}.chords: {e}")
            if need(s, "dynamic", str, w) and s["dynamic"] not in DYNAMICS:
                errs.append(f"{w}.dynamic: one of {DYNAMICS}")
            if need(s, "instruments", list, w):
                for j, ins in enumerate(s["instruments"]):
                    if not isinstance(ins, dict) or not {"name", "role"} <= set(ins):
                        errs.append(f"{w}.instruments[{j}]: needs name and role")
        if isinstance(p.get("global"), dict) and isinstance(p["global"].get("bars"), int) and prev_end and \
                prev_end != p["global"]["bars"]:
            errs.append(f"sections end at bar {prev_end}, global.bars is {p['global']['bars']}")
    if need(p, "motif", dict, "plan"):
        notes = p["motif"].get("notes")
        if not isinstance(notes, list) or not 2 <= len(notes) <= 12 or \
                not all(isinstance(n, list) and len(n) == 2 for n in notes):
            errs.append("motif.notes: 2-12 [midi, beats] pairs")
    if need(p, "rationale", list, "plan"):
        if not p["rationale"]:
            errs.append("rationale: say why, for at least the key decisions")
        for j, r in enumerate(p["rationale"]):
            if not isinstance(r, dict) or not {"decision", "why"} <= set(r):
                errs.append(f"rationale[{j}]: needs decision and why (source optional)")
    if "synth" in p and not (isinstance(p["synth"], str) and p["synth"].strip()):
        errs.append("synth: say why synthesized sound belongs in this piece, or leave the key out")
    return errs


def load(path):
    with open(path, encoding="utf-8") as fh:
        p = json.load(fh)
    errs = validate(p)
    if errs:
        raise PlanError(f"{path}:\n  " + "\n  ".join(errs))
    p["_path"] = str(path)
    return p


def chords(p):
    """One pitch-class list per bar for the whole piece (None for an unchecked 'N' bar). A section
    whose chord list is shorter than its length repeats it as a cycle."""
    out = []
    for s in p["sections"]:
        a, b = s["bars"]
        cyc = s["chords"]
        out += [chord_pcs(cyc[i % len(cyc)]) for i in range(b - a)]
    return out


def score(p, **kw):
    """A Score set up from the plan's global settings; keyword arguments override (seed, tail...)."""
    from .score import Score
    g = p["global"]
    args = dict(bpm=g["bpm"], bars=g["bars"], beats_per_bar=g["beats_per_bar"], loop=g["loop"],
                genre=g.get("genre"), reference=p.get("reference"), allow_synth=bool(p.get("synth")))
    if g.get("target_lufs") is not None:
        args["target_lufs"] = g["target_lufs"]
    args.update(kw)
    return Score(**args)


def summary(p):
    """A short readable version for approval."""
    g = p["global"]
    beat = 60 / g["bpm"]
    secs = g["bars"] * g["beats_per_bar"] * beat
    lines = [f"# {p['title']}  ({p['use']})", "", p["brief"], "",
             f"{g['bpm']} bpm, {g['beats_per_bar']}/4, {g['key']} {g['mode']}, {g['bars']} bars "
             f"(~{int(secs // 60)}:{int(secs % 60):02d}), {'seamless loop' if g['loop'] else 'one-shot'}"
             + (f", master preset {g['genre']}" if g.get("genre") else ""), ""]
    lines.append("| bars | section | chords | dynamic | who plays |")
    lines.append("|---|---|---|---|---|")
    for s in p["sections"]:
        who = ", ".join(f"{i['name']} ({i['role']})" for i in s["instruments"])
        ch = " ".join(c if isinstance(c, str) else str(c) for c in s["chords"])
        lines.append(f"| {s['bars'][0] + 1}-{s['bars'][1]} | {s['name']} - {s['function']} | {ch} | {s['dynamic']} | {who} |")
    m = p["motif"]
    names = "C C# D D# E F F# G G# A A# B".split()
    lines += ["", "Motif: " + " ".join(f"{names[n % 12]}{n // 12 - 1}({d:g})" for n, d in m["notes"])
              + (f" - {m['description']}" if m.get("description") else ""), "", "Why:"]
    lines += [f"- {r['decision']}: {r['why']}" + (f" [{r['source']}]" if r.get("source") else "") for r in p["rationale"]]
    if p.get("reference"):
        lines += ["", f"Reference: {p['reference']}"]
    if p.get("synth"):
        lines += ["", f"Synthesized sound: {p['synth']}"]
    return "\n".join(lines)


def main(argv):
    cmd, path = argv[0], argv[1]
    if cmd == "check":
        with open(path, encoding="utf-8") as fh:
            errs = validate(json.load(fh))
        print("\n".join(errs) if errs else f"{path}: OK")
        raise SystemExit(1 if errs else 0)
    if cmd == "summary":
        print(summary(load(path)))
        return
    raise SystemExit(f"plan: unknown subcommand {cmd!r} (check, summary)")
