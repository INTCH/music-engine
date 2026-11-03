"""Offline sampler + mixer.

Instruments are sets of real recorded notes ("zones"). A note is rendered by picking the
zone that covers it (or the nearest recorded root), repitching by resampling, stretching
sustains with crossfaded loops when the note is longer than the recording, and enveloping
it. Notes land on stems; stems go through a shared convolution hall and a master bus.
"""
import os
import re
import glob
import random
from collections import OrderedDict

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, fftconvolve, butter, sosfilt

SR = 48000

NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_RE = re.compile(r"(?:^|[_\s-])([A-Ga-g])([#b]?)(-?\d)(?=$|[_\s.-])")
DYN = {"ppp": 0, "pp": 1, "p": 2, "mp": 3, "mf": 4, "f": 5, "ff": 6, "fff": 7}


def note_to_midi(name):
    """'A4' -> 69, 'C#3' -> 49, 'Bb2' -> 46."""
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", name)
    n = NOTE_NAMES[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return n + 12 * (int(m.group(3)) + 1)


def parse_root(filename):
    m = NOTE_RE.search(os.path.splitext(os.path.basename(filename))[0])
    return note_to_midi("".join(m.groups())) if m else None


def parse_layer(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r"_v(\d+)", base)
    if m:
        return int(m.group(1))
    m = re.search(r"_(ppp|pp|p|mp|mf|f|ff|fff)(?=$|_)", base)
    if m:
        return DYN[m.group(1)]
    m = re.search(r"dyn(\d+)", base)
    return int(m.group(1)) if m else 0


_CACHE = OrderedDict()
CACHE_BYTES = int(os.environ.get("MUSICENGINE_CACHE_MB", "3000")) * 2 ** 20


def load(path):
    """Decoded, 48 kHz stereo, leading silence trimmed, peak-normalized -> (data, peak).
    Kept in a byte-capped LRU so long scores with many layers do not exhaust memory."""
    if path in _CACHE:
        _CACHE.move_to_end(path)
        return _CACHE[path]
    item = _load(path)
    _CACHE[path] = item
    total = sum(v[0].nbytes for v in _CACHE.values())
    while total > CACHE_BYTES and len(_CACHE) > 1:
        _, old = _CACHE.popitem(last=False)
        total -= old[0].nbytes
    return item


def _load(path):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :2]
    if sr != SR:
        g = np.gcd(SR, sr)
        data = resample_poly(data, SR // g, sr // g, axis=0).astype(np.float32)
    # trim leading silence so onsets land on the grid
    env = np.abs(data).max(axis=1)
    thr = env.max() * 0.02
    start = int(np.argmax(env > thr))
    start = max(0, start - int(0.004 * SR))
    data = data[start:]
    peak = np.abs(data).max() or 1.0
    return data / peak, peak


def velocity_gain(vel):
    """Loudness for a velocity 0..1, on top of whichever recorded layer plays."""
    return 0.25 + 0.75 * vel ** 1.6


_LEVELS = {}


LEVEL_METHOD = 3      # bump when sample_levels changes, so cached values are measured again


def sample_levels(path):
    """(body_db, peak_db) of a recorded sample. body: mean power of the 50 ms blocks within
    20 dB of the loudest one in the first 1.5 s after its start; peak: its sample peak.
    Measured once per file and kept in LIBRARY/_cache/levels.json (keyed by path, size, mtime)."""
    if not _LEVELS:
        _LEVELS.update(_levels_file_read())
    st = os.stat(path)
    stamp = [st.st_size, st.st_mtime_ns, LEVEL_METHOD]
    hit = _LEVELS.get(path)
    if hit and hit[:3] == stamp:
        return hit[3], hit[4]
    info = sf.info(path)
    x, sr = sf.read(path, frames=int(info.samplerate * 3), dtype="float32", always_2d=True)
    x = x[:, :2]
    env = np.abs(x).max(axis=1)
    x = x[max(0, int(np.argmax(env > env.max() * 0.02)) - int(0.004 * sr)):][: int(1.5 * sr)]
    b = int(0.05 * sr)
    nb = len(x) // b
    if nb == 0:
        body = float(10 * np.log10((x ** 2).mean() + 1e-12))
    else:
        e = (x[: nb * b] ** 2).reshape(nb, -1).mean(axis=1)
        body = float(10 * np.log10(e[e > e.max() * 0.01].mean() + 1e-12))
    peak = float(20 * np.log10(env.max() + 1e-12))
    _LEVELS[path] = stamp + [body, peak]
    _LEVELS["__dirty__"] = True
    return body, peak


def _levels_path():
    from .config import LIBRARY
    return LIBRARY / "_cache" / "levels.json"


def _levels_file_read():
    import json
    try:
        return json.loads(_levels_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _levels_flush():
    """Merge this process's measurements into the shared file (atomic replace; a lost race
    only means a file is measured again)."""
    import json
    if not _LEVELS.pop("__dirty__", False):
        return
    p = _levels_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = _levels_file_read()
        data.update(_LEVELS)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.part")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


class Instrument:
    """A playable set of zones.

    zones: either tuples (path, root_midi, layer) from filename rules - layers are ranked
    0..1 and the nearest recorded root is used - or dicts from an SFZ map
    (path, root, lokey, hikey, lovel, hivel, tune_cents, keytrack, gain_db), where the zone
    whose key/velocity range covers the note is used.

    smooth_layers: with several velocity layers, each note is set to a level that follows
    velocity continuously (keeping the layer's timbre): libraries record their layers 10-26 dB
    apart and single notes up to 15 dB off their neighbours, so a crescendo crossing a layer
    switch jumped. See layer_curve().
    speak: start each sample where it has grown to this fraction of its body level (minus
    10 ms, at most 500 ms in) - for slow-bowed recordings whose notes otherwise speak late.
    """

    def __init__(self, name, zones, sustain=True, attack=0.0, release=0.4,
                 gain=1.0, keep_level=True, tune=0.0, smooth_layers=True, speak=None):
        if not zones:
            raise ValueError(f"{name}: no zones")
        self.name = name
        self.sustain = sustain      # True -> loop to hold long notes
        self.attack = attack
        self.release = release
        self.gain = gain
        self.keep_level = keep_level  # keep recorded loudness differences between layers
        self.tune = tune
        self.speak = speak
        self._speak_at = {}
        self.mapped = isinstance(zones[0], dict)
        if self.mapped:
            self.zones = zones
            self.roots = np.array(sorted({z["root"] for z in zones}))
        else:
            layers = sorted({z[2] for z in zones})
            self.zones = [(p, r, layers.index(l) / max(1, len(layers) - 1)) for p, r, l in zones]
            self.roots = np.array(sorted({z[1] for z in self.zones}))
        self.curve = layer_curve(self) if smooth_layers and keep_level else None

    def level_db(self, vel, root):
        """Target loudness (dB, recorded scale) of a note at this velocity and sample root."""
        c = self.curve
        ys = [a + b * root for a, b in c["fits"]]
        return float(np.interp(vel, c["centres"], ys))

    def level_gain_db(self, path, gain_db, vel, root):
        """Gain that brings this sample to the smooth level, in two parts: its layer's line is
        moved to the level for this velocity, and the sample is moved onto its layer's line -
        that second part capped so its peak stays within 3 dB of the layer's typical peak (a
        pluck with a quiet body but a sharp attack is not raised until it towers over its
        neighbours)."""
        c = self.curve
        body, peak = c["db"][(path, gain_db)]
        layer = c["layer_of"][(path, gain_db)]
        a, b = c["fits"][layer]
        pa, pb = c["peaks"][layer]
        own = a + b * root
        g_note = min(own - body, pa + pb * root + 3.0 - peak)
        return min(18.0, max(-18.0, self.level_db(vel, root) - own + g_note))

    def speak_offset(self, path, data):
        if path not in self._speak_at:
            w = int(0.01 * SR)
            m = data[: int(1.5 * SR) + w].mean(axis=1)
            e = np.sqrt(np.convolve(m ** 2, np.ones(w) / w, mode="same"))[: int(1.5 * SR)]
            i = int(np.argmax(e >= np.percentile(e, 90) * self.speak))
            self._speak_at[path] = max(0, min(i - w, int(0.5 * SR)))
        return self._speak_at[path]

    @classmethod
    def from_glob(cls, name, pattern, root_fn=parse_root, layer_fn=parse_layer, **kw):
        """pattern: absolute glob. Raises (naming the pattern) when nothing usable matches."""
        files = sorted(glob.glob(pattern, recursive=True))
        zones = []
        for f in files:
            r = root_fn(f)
            if r is not None:
                zones.append((f, r, layer_fn(f)))
        if not zones:
            raise FileNotFoundError(f"{name}: no samples with a readable root match {pattern!r} "
                                    f"({len(files)} files matched)")
        return cls(name, zones, **kw)

    def pick(self, midi, vel, rng):
        """-> (path, root, tune_cents, keytrack, gain_db). `midi` only chooses the sample here;
        render() pitches it to the played note."""
        if self.mapped:
            v127 = max(1, min(127, int(round(vel * 127))))
            keyed = [z for z in self.zones if z["lokey"] <= midi <= z["hikey"]]
            if not keyed:
                root = int(self.roots[np.argmin(np.abs(self.roots - midi))])
                keyed = [z for z in self.zones if z["root"] == root]
            inside = [z for z in keyed if z["lovel"] <= v127 <= z["hivel"]]
            if not inside:
                d = min(min(abs(z["lovel"] - v127), abs(z["hivel"] - v127)) for z in keyed)
                inside = [z for z in keyed if min(abs(z["lovel"] - v127), abs(z["hivel"] - v127)) == d]
            z = rng.choice(inside)
            return z["path"], z["root"], z["tune_cents"], z["keytrack"], z["gain_db"]
        root = int(self.roots[np.argmin(np.abs(self.roots - midi) + (self.roots > midi) * 0.1)])
        cands = [z for z in self.zones if z[1] == root]
        best = min(abs(z[2] - vel) for z in cands)
        cands = [z for z in cands if abs(z[2] - vel) <= best + 1e-6]
        path, root, _ = rng.choice(cands)
        return path, root, 0.0, True, 0.0

    def render(self, midi, dur, vel=0.7, rng=random, attack=None, release=None, cents=0.0, near=None):
        """near: choose the sample recorded for this note instead of `midi` (an ensemble uses it
        so each voice is a different recording, pitched to the same note)."""
        path, root, ztune, keytrack, gain_db = self.pick(midi if near is None else near, vel, rng)
        data, peak = load(path)
        if gain_db:
            peak = peak * 10 ** (gain_db / 20)
        if self.speak:
            data = data[self.speak_offset(path, data):]
        if self.curve and (path, gain_db) in self.curve["db"]:
            peak = peak * 10 ** (self.level_gain_db(path, gain_db, vel, root) / 20)
        attack = self.attack if attack is None else attack
        release = self.release if release is None else release
        semis = (midi - root) if keytrack else 0
        ratio = 2 ** (semis / 12 + (cents + self.tune + ztune) / 1200)
        out_len = int((dur + release) * SR)
        need = int(out_len * ratio) + 4
        if self.sustain and need > len(data):
            data = extend(data, need, rng)
        pos = np.arange(out_len) * ratio
        pos = pos[pos < len(data) - 1]
        x = np.empty((len(pos), 2), np.float32)
        for c in range(2):
            x[:, c] = np.interp(pos, np.arange(len(data)), data[:, c])
        n = len(x)
        envl = np.ones(n, np.float32)
        a = min(n, int(attack * SR))
        if a > 0:
            envl[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
        rs = int(dur * SR)
        if rs < n:
            rl = n - rs
            envl[rs:] *= np.cos(np.linspace(0, np.pi / 2, rl)) ** 2
        level = (peak if self.keep_level else 1.0) * velocity_gain(vel) * self.gain
        return x * envl[:, None] * level


def layer_curve(inst):
    """Velocity -> loudness for an instrument with several velocity layers, or None.

    Per layer, the recorded body loudness of its samples (sample_levels) is fitted as a line
    over pitch, which keeps the register's natural slope and drops single notes recorded too
    loud or soft; their peaks get a line too (Instrument.level_gain_db caps with it). The
    layer's centre velocity anchors those lines, and a note's target level is interpolated
    between the layers' lines at its velocity - so loudness moves smoothly through a layer
    switch while the sample (timbre) still changes there. A layer whose velocity range
    contains another one's (an SFZ catch-all) is not used as an anchor."""
    groups = {}
    if inst.mapped:
        for z in inst.zones:
            groups.setdefault((z["lovel"], z["hivel"]), []).append((z["path"], z["root"], z["gain_db"]))
        spans = list(groups)
        anchors = {k: (k[0] + k[1]) / 2 / 127 for k in spans
                   if not any(o != k and k[0] <= o[0] and o[1] <= k[1] for o in spans)}
    else:
        for p, r, layer in inst.zones:
            groups.setdefault(layer, []).append((p, r, 0.0))
        anchors = {k: k for k in groups}
    if len(anchors) < 2:
        return None
    db = {}
    for members in groups.values():
        for p, _, g in members:
            if (p, g) not in db:
                body, peak = sample_levels(p)
                db[(p, g)] = (body + g, peak + g)
    _levels_flush()

    def line(roots, ys):
        slope = 0.0
        if len(set(roots)) >= 3:
            slope = float(np.clip(np.polyfit(roots, ys, 1)[0], -0.5, 0.5))
        return float(ys.mean() - slope * roots.mean()), slope

    centres, fits, peaks, layer_of = [], [], [], {}
    for i, k in enumerate(sorted(anchors, key=anchors.get)):
        roots = np.array([r for _, r, _ in groups[k]], float)
        fits.append(line(roots, np.array([db[(p, g)][0] for p, _, g in groups[k]])))
        peaks.append(line(roots, np.array([db[(p, g)][1] for p, _, g in groups[k]])))
        centres.append(anchors[k])
        for p, _, g in groups[k]:
            layer_of.setdefault((p, g), i)
    for k, members in groups.items():      # catch-all samples: the layer they sound closest to
        for p, r, g in members:
            if (p, g) not in layer_of:
                layer_of[(p, g)] = int(np.argmin([abs(a + b * r - db[(p, g)][0]) for a, b in fits]))
    return dict(centres=centres, fits=fits, peaks=peaks, db=db, layer_of=layer_of)


class Ensemble:
    """A section built from one recorded performer, the way a singer is stacked in a studio:
    every voice plays a *different* recording (the sample of a neighbouring note, pitched to
    the target), entering a few ms apart, slightly out of tune with the others and placed
    across the stereo field. Using distinct recordings per voice avoids the comb-filter
    sound of one sample copied onto itself. No synthesis: only the source's recordings."""

    def __init__(self, name, base, voices=6, detune_cents=7.0, spread_s=0.035, donors=2,
                 attack=None, release=None, lo=None, hi=None):
        self.name = name
        self.base = base
        self.voices = voices
        self.detune = detune_cents
        self.spread = spread_s
        self.donors = donors
        self.attack = attack
        self.release = release
        self.roots = base.roots
        self.lo = int(base.roots.min()) if lo is None else lo     # comfortable range, for callers
        self.hi = int(base.roots.max()) if hi is None else hi

    def render(self, midi, dur, vel=0.7, rng=random, attack=None, release=None, cents=0.0, near=None):
        attack = self.attack if attack is None else attack
        release = self.release if release is None else release
        lo, hi = int(self.roots.min()), int(self.roots.max())
        offsets = [0]
        for d in range(1, self.donors + 1):
            offsets += [-d, d]
        parts = []
        for v in range(self.voices):
            donor = min(hi, max(lo, (midi if near is None else near) + offsets[v % len(offsets)]))
            delay = int(rng.uniform(0, self.spread) * SR)
            x = self.base.render(midi, max(0.05, dur - delay / SR), vel * rng.uniform(0.85, 1.0), rng,
                                 attack=attack, release=release, cents=cents + rng.gauss(0, self.detune),
                                 near=donor)
            pan = (v / max(1, self.voices - 1)) * 1.4 - 0.7 if self.voices > 1 else 0.0
            g = np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)], np.float32) * np.sqrt(2)
            parts.append(np.concatenate([np.zeros((delay, 2), np.float32), x * g]))
        n = max(len(p) for p in parts)
        out = np.zeros((n, 2), np.float32)
        for p in parts:
            out[:len(p)] += p
        return out / np.sqrt(self.voices)


def extend(data, need, rng, xf=0.35):
    """Lengthen a sustained recording by chaining crossfaded chunks of its steady part."""
    n = len(data)
    a, b = int(n * 0.30), int(n * 0.88)
    xfl = min(int(xf * SR), (b - a) // 3)
    if b - a < 2 * xfl + 10:
        return np.concatenate([data, np.zeros((need - n, 2), np.float32)])
    fade_in = np.sin(np.linspace(0, np.pi / 2, xfl))[:, None] ** 2
    fade_out = 1 - fade_in
    out = [data[:b - xfl]]
    tail = data[b - xfl:b]
    total = b - xfl
    while total < need:
        s = rng.randint(a, max(a + 1, b - xfl * 3))
        e = rng.randint(s + xfl * 2, b)
        chunk = data[s:e]
        joined = tail * np.sqrt(fade_out) + chunk[:xfl] * np.sqrt(fade_in)
        body = chunk[xfl:len(chunk) - xfl]
        out += [joined, body]
        tail = chunk[len(chunk) - xfl:]
        total += len(joined) + len(body)
    out.append(tail * fade_out)
    return np.concatenate(out).astype(np.float32)


# ---------------------------------------------------------------- synthesis

def synth_pad(freqs, dur, detune=0.12, voices=5, cutoff=1800, attack=2.0, release=3.0,
              rng=None, brightness_lfo=0.07):
    """Warm analog-style pad: detuned saws (band-limited additive), slow filter movement."""
    rng = rng or np.random.default_rng(1)
    n = int((dur + release) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2), np.float32)
    for f in freqs:
        for v in range(voices):
            det = 2 ** (detune * (v - (voices - 1) / 2) / 12 / 2)
            ff = f * det
            ph = rng.uniform(0, 2 * np.pi)
            kmax = int(min(40, (SR / 2) / ff))
            sig = np.zeros(n)
            for k in range(1, kmax + 1):
                amp = 1 / k * (1 / (1 + (k * ff / cutoff) ** 2))
                if amp < 1e-3:
                    break
                sig += amp * np.sin(2 * np.pi * ff * k * t + ph * k)
            pan = (v / max(1, voices - 1)) * 2 - 1
            out[:, 0] += sig * np.sqrt((1 - pan * 0.8) / 2)
            out[:, 1] += sig * np.sqrt((1 + pan * 0.8) / 2)
    lfo = 1 + 0.25 * np.sin(2 * np.pi * brightness_lfo * t + rng.uniform(0, 6))
    out *= lfo[:, None]
    out *= adsr(n, attack, release, dur)[:, None]
    return out / (np.abs(out).max() + 1e-9)


def synth_sub(freq, dur, attack=1.5, release=2.0):
    n = int((dur + release) * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(4 * np.pi * freq * t)
    env = adsr(n, attack, release, dur)
    return np.repeat((sig * env)[:, None], 2, axis=1).astype(np.float32) / 1.18


def synth_pulse(freq, dur, rate_hz, rng=None, cutoff=900):
    """Throbbing low synth used for tension: filtered saw with rhythmic gate."""
    rng = rng or np.random.default_rng(2)
    n = int(dur * SR)
    t = np.arange(n) / SR
    saw = 2 * ((freq * t) % 1.0) - 1
    saw2 = 2 * ((freq * 1.004 * t + 0.3) % 1.0) - 1
    sig = 0.5 * (saw + saw2)
    sos = butter(2, cutoff, "low", fs=SR, output="sos")
    sig = sosfilt(sos, sig)
    gate = 0.5 - 0.5 * np.cos(2 * np.pi * rate_hz * t)
    gate = gate ** 2.5
    out = np.repeat((sig * gate)[:, None], 2, axis=1).astype(np.float32)
    return out / (np.abs(out).max() + 1e-9)


def noise_wind(dur, lo=200, hi=2500, sweep=0.03, rng=None):
    """Slowly sweeping band-passed noise - the 'vacuum' bed."""
    rng = rng or np.random.default_rng(3)
    n = int(dur * SR)
    noise = rng.standard_normal((n, 2)).astype(np.float32)
    sos = butter(2, [lo, hi], "band", fs=SR, output="sos")
    x = sosfilt(sos, noise, axis=0)
    t = np.arange(n) / SR
    env = 0.6 + 0.4 * np.sin(2 * np.pi * sweep * t)[:, None]
    return (x * env / (np.abs(x).max() + 1e-9)).astype(np.float32)


def adsr(n, attack, release, dur):
    env = np.ones(n, np.float32)
    a = min(n, int(attack * SR))
    if a:
        env[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    rs = min(n, int(dur * SR))
    if rs < n:
        env[rs:] *= np.cos(np.linspace(0, np.pi / 2, n - rs)) ** 2
    return env


# ---------------------------------------------------------------- mixing

def hall_ir(seconds=5.0, predelay=0.03, damp_hz=(9000, 4500, 2200), seed=7):
    """Synthetic stereo concert-hall impulse: decorrelated noise, high bands decay faster."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2), np.float32)
    bands = [(None, 400, 1.0), (400, 2000, 0.85), (2000, 6000, 0.6), (6000, None, 0.35)]
    for lo, hi, decay_scale in bands:
        noise = rng.standard_normal((n, 2))
        if lo and hi:
            sos = butter(2, [lo, hi], "band", fs=SR, output="sos")
        elif hi:
            sos = butter(2, hi, "low", fs=SR, output="sos")
        else:
            sos = butter(2, lo, "high", fs=SR, output="sos")
        band = sosfilt(sos, noise, axis=0)
        t60 = seconds * 0.75 * decay_scale
        ir += (band * np.exp(-6.9 * t / t60)[:, None]).astype(np.float32)
    # soft onset of the diffuse field
    ramp = int(0.02 * SR)
    ir[:ramp] *= np.linspace(0, 1, ramp)[:, None]
    pd = np.zeros((int(predelay * SR), 2), np.float32)
    ir = np.concatenate([pd, ir])
    return ir / np.sqrt((ir ** 2).sum(axis=0, keepdims=True))


def ping_pong(x, seconds, feedback, wet, lp_hz, taps=10):
    """Echo repeats alternating left/right, each one darker and quieter (returns only the wet part)."""
    out = np.zeros_like(x)
    d = int(seconds * SR)
    mono = x.mean(axis=1)
    sos = butter(1, lp_hz, "low", fs=SR, output="sos")
    sig = mono
    for k in range(1, taps + 1):
        sig = sosfilt(sos, sig)
        g = wet * feedback ** (k - 1)
        if g < 1e-3 or k * d >= len(x):
            break
        ch = (k + 1) % 2                      # first repeat right, then left, ...
        out[k * d:, ch] += sig[: len(x) - k * d] * g
        out[k * d:, 1 - ch] += sig[: len(x) - k * d] * g * 0.25
    return out


def synth_glass(freq, dur, decay=4.0, attack=0.04, rng=None):
    """Glass-harmonica-like tone: pure partial plus faint inharmonic glass partials, slow shimmer.
    Clean sines only - no noise."""
    rng = rng or np.random.default_rng(9)
    n = int((dur + decay) * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    # harmonic partials only: an inharmonic 2.76x partial was measured landing out of key
    for ratio, amp, dec in ((1.0, 1.0, 1.0), (2.0, 0.18, 0.6), (3.0, 0.05, 0.35), (4.0, 0.02, 0.2)):
        f = freq * ratio
        if f > SR / 2.2:
            continue
        sig += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t / (decay * dec))
    sig *= 1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)          # gentle tremolo shimmer
    env = adsr(n, attack, decay, dur)
    out = np.stack([sig * env, np.roll(sig * env, int(0.011 * SR))], axis=1)
    return (out / (np.abs(out).max() + 1e-9)).astype(np.float32)


def synth_kick(freq=48.0, pitch_from=110.0, decay=0.42, click=0.0):
    """Soft rounded electronic kick: sine with a quick pitch drop, no click by default."""
    n = int((decay * 2.5) * SR)
    t = np.arange(n) / SR
    f = freq + (pitch_from - freq) * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-t / decay) * (1 - np.exp(-t / 0.002))
    sig = np.sin(ph) * env
    if click:
        sig += click * np.random.default_rng(5).standard_normal(n) * np.exp(-t / 0.003)
    return np.repeat(sig[:, None], 2, axis=1).astype(np.float32)


class Mix:
    def __init__(self, length_s, clock=None):
        """clock={"offset": s, "period": s or None}: where score time 0 sits in the buffer and
        the loop length. Automation times (sweep points, duck times) are then score time, and
        LFO rates (fx, autopan) are rounded to whole cycles per loop so the seam stays smooth."""
        self.n = int(length_s * SR)
        self.stems = {}
        self.cfg = {}
        self.clock = clock

    def stem(self, name, level_db=-20.0, pan=0.0, width=1.0, reverb=0.3, hp=None, lp=None,
             delay=None, autopan=None, fx=None):
        """level_db: loudness of the stem while it is playing (its 'active' RMS).
        Libraries are recorded at different levels, so balance is set by role, not raw gain;
        dynamics inside a stem still come from note velocities.
        delay=(seconds, feedback, wet, lowpass_hz): ping-pong echo after leveling.
        autopan=(rate_hz, depth): slow left-right drift.
        fx=[("amp", {"voicing": "crunch"}), ("duck", {"key": "kick"}), ...]: musicengine.fx
        chain, run on the stem at a nominal -18 dBFS before it is leveled to level_db."""
        if name not in self.stems:
            self.stems[name] = np.zeros((self.n, 2), np.float32)
        self.cfg[name] = dict(level_db=level_db, pan=pan, width=width, reverb=reverb, hp=hp, lp=lp,
                              delay=delay, autopan=autopan, fx=fx)
        return name

    def add(self, name, audio, at_s, gain=1.0):
        i = int(at_s * SR)
        if i < 0:
            audio, i = audio[-i:], 0
        if i >= self.n or len(audio) == 0:
            return
        j = min(self.n, i + len(audio))
        self.stems[name][i:j] += audio[: j - i] * gain

    def render(self, ir, stems=False):
        """-> (mix, levels) or, with stems=True, (mix, levels, {stem: its dry + its own reverb})."""
        dry = np.zeros((self.n, 2), np.float32)
        send = np.zeros((self.n, 2), np.float32)
        levels = {}
        buses = {}
        for name, x in self.stems.items():
            c = self.cfg[name]
            y = x
            if c.get("fx"):
                from . import fx as fxmod
                y = y * (10 ** (-18 / 20) / (active_rms(y) + 1e-12))
                y = fxmod.chain(y, c["fx"], stems=self.stems, clock=self.clock)
            if c["hp"]:
                y = sosfilt(butter(2, c["hp"], "high", fs=SR, output="sos"), y, axis=0)
            if c["lp"]:
                y = sosfilt(butter(2, c["lp"], "low", fs=SR, output="sos"), y, axis=0)
            mid = (y[:, 0] + y[:, 1]) / 2
            side = (y[:, 0] - y[:, 1]) / 2 * c["width"]
            l, r = mid + side, mid - side
            p = c["pan"]
            l *= np.sqrt((1 - p) / 2) * np.sqrt(2)
            r *= np.sqrt((1 + p) / 2) * np.sqrt(2)
            y = np.stack([l, r], axis=1).astype(np.float32)
            y *= 10 ** (c["level_db"] / 20) / (active_rms(y) + 1e-12)
            levels[name] = 20 * np.log10(active_rms(y) + 1e-12)
            if c["autopan"]:
                rate, depth = c["autopan"]
                if self.clock:
                    from .fx import loop_rate
                    rate = loop_rate(rate, self.clock.get("period"))
                ph = np.sin(2 * np.pi * rate * np.arange(self.n) / SR) * depth
                y = y * np.stack([np.sqrt(1 - ph), np.sqrt(1 + ph)], axis=1).astype(np.float32)
            if c["delay"]:
                y = y + ping_pong(y, *c["delay"])
            dry += y * (1 - c["reverb"] * 0.5)
            send += y * c["reverb"]
            if stems:
                own = np.stack([fftconvolve(y[:, ch] * c["reverb"], ir[:, ch])[: self.n] for ch in range(2)], axis=1)
                buses[name] = (y * (1 - c["reverb"] * 0.5) + own.astype(np.float32) * 0.9).astype(np.float32)
        wet = np.stack([fftconvolve(send[:, ch], ir[:, ch])[: self.n] for ch in range(2)], axis=1)
        out = dry + wet.astype(np.float32) * 0.9
        if stems:
            return out, levels, buses
        return out, levels


def active_rms(y, block=0.4):
    """RMS over the blocks where the stem is actually sounding (within 30 dB of its loudest)."""
    b = int(block * SR)
    nb = len(y) // b
    if nb == 0:
        return float(np.sqrt((y ** 2).mean()))
    e = (y[: nb * b] ** 2).reshape(nb, b, 2).mean(axis=(1, 2))
    on = e > e.max() * 1e-3
    return float(np.sqrt(e[on].mean())) if on.any() else 0.0


def write(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, x, SR, subtype="PCM_24")
