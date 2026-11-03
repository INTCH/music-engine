"""Composition helpers: a beat grid, chord voicing, seamless-loop / one-shot rendering,
and a JSON sidecar recording what each render depended on."""
import datetime
import json
import random
import subprocess

import numpy as np

from . import catalog
from .config import REPO
from .engine import SR, Mix, load, hall_ir, write


def get(name):
    return catalog.get(name)


def _package_version():
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version("musicengine")
    except (ImportError, PackageNotFoundError):
        return "unknown"


def engine_version():
    """`git describe` of the source checkout when there is one, else the installed package version."""
    if (REPO / ".git").exists():
        try:
            r = subprocess.run(["git", "-C", str(REPO), "describe", "--always", "--dirty", "--tags"],
                               capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except OSError:
            pass
    return _package_version()

PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
      "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def chord(root, *intervals):
    """chord('A', 0, 3, 7, 14) -> pitch classes, root first."""
    r = PC[root]
    return [(r + i) % 12 for i in intervals]


def voice(pcs, lo, hi):
    """Every chord tone between lo and hi (MIDI), ascending."""
    return [m for m in range(lo, hi + 1) if m % 12 in pcs]


def bass(pcs, lo=36):
    r = pcs[0]
    return lo + ((r - lo) % 12)


def chord_run(cycle, bar):
    """Bars the chord starting at `bar` lasts, or 0 if `bar` continues the previous chord.
    Sustained parts must be placed per chord, not per fixed bar count, or a held note
    spills over the next chord."""
    n = len(cycle)
    if bar % n and cycle[bar % n] == cycle[bar % n - 1]:
        return 0
    k = 1
    while (bar % n) + k < n and cycle[(bar % n) + k] == cycle[bar % n]:
        k += 1
    return k


class Score:
    def __init__(self, bpm, bars, beats_per_bar=4, seed=1, pre=16.0, post=3.0, loop=True, tail=10.0,
                 allow_synth=False, genre=None, target_lufs=-16.0, ceiling_dbtp=-1.0, reference=None):
        """loop=False: a one-shot cue with a beginning and an end; the reverb tail is kept
        (`tail` seconds) and nothing wraps around.
        allow_synth=False: render() refuses software-synthesized sources (synth/… patches,
        the built-in drum kits, libraries listed in catalog_data/synthetic.toml) - recordings
        only, hardware synths included. Audio passed to audio() is not checked.
        The master is musicengine.mastering (genre EQ, glue, true-peak limiter, LUFS target).
        genre: a mastering preset (mastering.PRESETS); it also gives stem(..., role=...) its fx.
        reference: a reference.json (python -m musicengine reference) whose tonal balance the
        master leans toward."""
        self.allow_synth = allow_synth
        self.genre = genre
        self.target_lufs = target_lufs
        self.ceiling_dbtp = ceiling_dbtp
        self.reference = reference
        if genre is not None:
            from .mastering import preset
            preset(genre)                    # unknown genre: fail now, not after placing every note
        self.beat = 60.0 / bpm
        self.bpb = beats_per_bar
        self.bars = bars
        self.L = bars * beats_per_bar * self.beat
        self.loop = loop
        if not loop:
            pre, post = 0.5, tail
        self.pre = pre
        self.post = post     # loop: start of the next cycle, so filters/limiter see the real continuation
        clock = dict(offset=pre, period=self.L if loop else None)
        self.mix = Mix(self.L + pre + post, clock=clock)
        self.events = []
        self.rng = random.Random(seed)
        catalog.USED.clear()          # credits/sidecar list only what this score uses

    def t(self, bar, beat=0.0):
        """Score time in seconds. Stem automation (sweep points, duck times) takes it as is: the
        pre-roll is added for you."""
        return (bar * self.bpb + beat) * self.beat

    def stem(self, name, role=None, **kw):
        """role (drums, bass, percussion, guitar, keys, vocal...): with Score(genre=...), the
        genre preset's fx chain for that role runs before any fx given here."""
        if role:
            from .mastering import role_fx
            kw["fx"] = role_fx(self.genre, role) + list(kw.get("fx") or [])
        return self.mix.stem(name, **kw)

    def note(self, stem, inst, bar, beat, beats, midi, vel=0.6, human=0.006, **kw):
        t = self.t(bar, beat) + self.rng.uniform(-human, human)
        v = min(1.0, max(0.02, vel + self.rng.uniform(-0.04, 0.04)))
        self.events.append(("note", stem, inst, max(0.0, t), beats * self.beat, midi, v, kw))

    def notes(self, stem, inst, bar, beat, beats, midis, vel=0.6, **kw):
        for m in midis:
            self.note(stem, inst, bar, beat, beats, m, vel, **kw)

    def line(self, stem, inst, notes, legato=True, phrase=True, swell_long="hairpin", long_beats=2.0,
             human=0.006, xf=0.07, rit=0.08, **kw):
        """A melodic line played like a player would (musicengine.perform):
        notes: [(bar, beat, beats, midi, vel), ...] or with a 6th item, a dict of per-note options
        such as {"swell": "cresc"} or {"swell": None} to keep a long note flat.
        legato: notes that touch are joined (the next one enters past its attack, crossfaded).
        phrase: velocities arch to the phrase's highest note, the end tapers and relaxes.
        rit: how far (beats) a phrase's last onset relaxes late; lower it for rhythmic,
        detached lines that must sit on the accompaniment's grid.
        swell_long: the swell long notes (>= long_beats) get unless they set their own.
        Other keywords (attack, release, cents) go to every note. Not for chords: one voice."""
        from .perform import phrase as shape
        rows = []
        for n in sorted(notes, key=lambda n: (n[0], n[1])):
            bar, beat, beats, midi, vel = n[:5]
            opts = dict(n[5]) if len(n) > 5 else {}
            rows.append((bar * self.bpb + beat, beats, midi, vel, opts))
        if phrase:
            rows = shape(rows, rit=rit)
        items = []
        for b, beats, midi, vel, opts in rows:
            o = dict(kw)
            o.update(opts)
            if "swell" not in o and swell_long and beats >= long_beats:
                o["swell"] = swell_long
            t = b * self.beat + self.rng.uniform(-human, human)
            v = min(1.0, max(0.02, vel + self.rng.uniform(-0.04, 0.04)))
            items.append((max(0.0, t), beats * self.beat, midi, v, o))
        self.events.append(("line", stem, inst, items, dict(legato=legato, xf=xf)))

    def hit(self, stem, path, bar, beat=0.0, gain=1.0):
        self.events.append(("hit", stem, path, self.t(bar, beat), gain))

    def audio(self, stem, x, bar, beat=0.0, gain=1.0):
        self.events.append(("audio", stem, x, self.t(bar, beat), gain))

    def _place(self, stem, x, t, gain):
        self.mix.add(stem, x, self.pre + t, gain)
        if not self.loop:
            return
        if t + len(x) / SR > self.L - self.pre:      # previous loop cycle bleeding into this one
            self.mix.add(stem, x, t - self.L + self.pre, gain)
        if t < self.post:                               # next loop cycle starting
            self.mix.add(stem, x, t + self.L + self.pre, gain)

    def render(self, out_base, ir_seconds=5.5, stems=False, midi=False):
        """Loop: master the whole pre+cycle+post render, then cut one cycle.
        The master levels to Score(target_lufs=...). With stems=True it skips its glue
        compressor (see mastering.master).
        One-shot: keep the reverb tail and fade the last second to silence.
        stems=True also writes <out_base>_stems/<stem>.wav: each stem with its own reverb and
        the mix's master gain/limiter applied, so the stems sum back to the mix (for adaptive
        game music). midi=True also writes <out_base>.mid (one track per stem)."""
        synthetic = self.synthetic_sources()
        if synthetic and not self.allow_synth:
            lines = "\n".join(f"  {n}: {why}" for n, why in sorted(synthetic.items()))
            raise ValueError("this score uses synthesized sound, and recordings only is the default:\n"
                             f"{lines}\nreplace them with recorded instruments, or pass "
                             "Score(..., allow_synth=True)")
        from . import mastering
        self.place_all()
        res = self.mix.render(hall_ir(ir_seconds), stems=stems)
        out, levels = res[0], res[1]
        start, end = int(self.pre * SR), int(self.pre * SR) + int(self.L * SR)
        gains = {}
        match = None
        if self.reference:
            with open(self.reference, encoding="utf-8") as fh:
                match = json.load(fh)["bands"]
        out, master_info = mastering.master(out, self.target_lufs, self.ceiling_dbtp, region=(start, end),
                                            genre=self.genre, match=match, gains=gains, glue=not stems)
        gr = 1 - 10 ** (-master_info["limiter_max_gr_db"] / 20)

        def cut(x):
            if self.loop:
                return x[start:end]
            x = x[start:].copy()
            f = int(1.0 * SR)
            x[-f:] *= np.cos(np.linspace(0, np.pi / 2, f))[:, None] ** 2
            return x
        out = cut(out)
        write(out_base + ".wav", out)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out_base + ".wav",
                        "-c:a", "libvorbis", "-q:a", "6", out_base + ".ogg"], check=True)
        stem_files = []
        if stems:
            for name, y in res[2].items():
                p = f"{out_base}_stems/{name}.wav"
                write(p, cut(mastering.master_stem(y, gains)))
                stem_files.append(p)
        if midi:
            from .midi import export_score
            export_score(self, out_base + ".mid")
        from . import loudness
        import soundfile as sf
        lv = loudness.measure(out)
        lv["ogg_true_peak_db"] = round(loudness.true_peak_db(sf.read(out_base + ".ogg", dtype="float32")[0]), 2)
        side = dict(rendered=datetime.datetime.now().isoformat(timespec="seconds"),
                    engine=engine_version(), seconds=round(len(out) / SR, 2), loop=self.loop,
                    bpm=round(60 / self.beat, 3), beats_per_bar=self.bpb, bars=self.bars,
                    master=master_info, loudness=lv, instruments=catalog.provenance(),
                    licenses=sorted({v["license"] for v in catalog.provenance().values()}),
                    recorded_only=not synthetic, synthetic=synthetic,
                    credits=catalog.credits(), stems=stem_files)
        self.loudness = lv
        with open(out_base + ".render.json", "w", encoding="utf-8") as fh:
            json.dump(side, fh, indent=1)
        return out, levels, gr

    def synthetic_sources(self):
        """{instrument or file: why it is not a recording} for everything this score plays."""
        out = {}
        for ev in self.events:
            if ev[0] in ("note", "line") and ev[2] not in out:
                why = catalog.synthetic(ev[2])
                if why:
                    out[ev[2]] = why
            elif ev[0] == "hit" and ev[2] not in out:
                why = catalog.synthetic_path(ev[2])
                if why:
                    out[ev[2]] = why
        return out

    def place_all(self):
        """Render every event onto the mix's stems (render() calls this)."""
        for ev in self.events:
            kind, stem = ev[0], ev[1]
            if kind == "note":
                _, _, inst, t, dur, midi, v, kw = ev
                if kw.get("swell"):
                    from .perform import render_note
                    kw = dict(kw)
                    swell = kw.pop("swell")
                    x = render_note(get(inst), midi, dur, v, self.rng, swell=swell, **kw)
                else:
                    kw = {k: val for k, val in kw.items() if k != "swell"}
                    x = get(inst).render(midi, dur, v, rng=self.rng, **kw)
                self._place(stem, x, t, 1.0)
            elif kind == "line":
                from .perform import render_line
                _, _, inst, items, opts = ev
                x, t0 = render_line(get(inst), items, self.rng, **opts)
                self._place(stem, x, t0, 1.0)
            elif kind == "hit":
                _, _, path, t, gain = ev
                x, peak = load(path)
                self._place(stem, x * peak, t, gain)
            else:
                _, _, x, t, gain = ev
                self._place(stem, x, t, gain)
