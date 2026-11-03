"""Audio effects for stems and the master bus. All offline, numpy/scipy, stereo float32 (n, 2).

Used through Mix.stem(fx=[("name", {params}), ...]) or called directly:
    y = fx.amp(x, gain=8, voicing="crunch")

Time-varying effects (phaser, filter sweeps, compressor gain) run at a control rate and are
interpolated, so a full track renders in seconds without per-sample Python loops.

LFO effects take period=: the loop length in seconds. Their rates are then rounded to a whole
number of cycles per loop, so the modulation at the loop's end meets its start (Score passes
it for loop renders; one-shots keep the exact rates).
"""
import numpy as np
from scipy.signal import lfilter, butter, sosfilt, resample_poly
from scipy.ndimage import maximum_filter1d

SR = 48000


def _f32(x):
    return np.asarray(x, dtype=np.float32)


def _db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def loop_rate(rate, period):
    """rate (Hz) rounded to a whole number of cycles per `period` seconds (at least one);
    period=None leaves it alone."""
    if not period or not rate:
        return rate
    return max(1, round(rate * period)) / period


# ------------------------------------------------------------------ biquads (RBJ cookbook)

def biquad(kind, f, q=0.707, gain_db=0.0, sr=SR):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * min(f, sr * 0.49) / sr
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2 * q)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "bp":
        b = [al, 0, -al]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "notch":
        b = [1, -2 * cw, 1]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "peak":
        b = [1 + al * A, -2 * cw, 1 - al * A]; a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind == "lowshelf":
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
        a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
    elif kind == "highshelf":
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
        a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    elif kind == "allpass":
        b = [1 - al, -2 * cw, 1 + al]; a = [1 + al, -2 * cw, 1 - al]
    else:
        raise ValueError(kind)
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return b, a


def eq(x, bands):
    """bands: list of (kind, freq, gain_db, q) - kind in lp/hp/bp/notch/peak/lowshelf/highshelf.
    eq(x, [("hp", 80), ("peak", 3000, -4, 1.2), ("highshelf", 10000, 2)])"""
    y = _f32(x)
    for band in bands:
        kind, f = band[0], band[1]
        g = band[2] if len(band) > 2 else 0.0
        q = band[3] if len(band) > 3 else 0.707
        b, a = biquad(kind, f, q, g)
        y = lfilter(b, a, y, axis=0)
    return _f32(y)


def sweep(x, kind="lp", start=200.0, end=8000.0, q=0.9, curve="exp", block=256, points=None,
          offset=0.0, period=None):
    """Time-varying filter (filter automation). Either a start->end ramp over the whole clip,
    or points=[(t_seconds, freq), ...] breakpoints. Coefficients change per block.
    Point times count from `offset` seconds into x; with period= they repeat every period
    seconds (interpolating from the last point round to the first). In a Score stem both are
    set for you, so points are score time: s.t(bar, beat)."""
    y = np.empty_like(_f32(x))
    n = len(x)
    if points:
        ts, fs = zip(*sorted(points))
        centers = (np.arange(0, n, block) + block / 2) / SR - offset
        freqs = np.exp(np.interp(centers, ts, np.log(fs), period=period))
    else:
        k = np.linspace(0, 1, (n + block - 1) // block)
        freqs = start * (end / start) ** k if curve == "exp" else start + (end - start) * k
    zi = np.zeros((2, x.shape[1]))
    for i, f in enumerate(freqs):
        s = slice(i * block, min(n, (i + 1) * block))
        b, a = biquad(kind, f, q)
        # direct form II transposed state carries over between blocks
        y[s], zi = lfilter(b, a, x[s], axis=0, zi=zi)
    return y


# ------------------------------------------------------------------ dynamics

def _envelope(level, attack, release, rate):
    """One-pole attack/release follower on a control-rate signal (Python loop at ~1.5 kHz)."""
    ga = np.exp(-1.0 / max(1, attack * rate))
    gr = np.exp(-1.0 / max(1, release * rate))
    env = np.empty_like(level)
    e = 0.0
    for i, v in enumerate(level):
        g = ga if v > e else gr
        e = g * e + (1 - g) * v
        env[i] = e
    return env


def compressor(x, threshold_db=-18.0, ratio=4.0, attack=0.01, release=0.15, makeup_db=0.0,
               knee_db=6.0, key=None, mix=1.0, ctrl=32):
    """Feed-forward compressor; key = optional sidechain signal (same length) to detect from."""
    x = _f32(x)
    det = np.abs(key if key is not None else x)
    det = det.max(axis=1) if det.ndim == 2 else det
    n = len(det)
    m = (n + ctrl - 1) // ctrl
    pad = np.zeros(m * ctrl, np.float32)
    pad[:n] = det
    level = pad.reshape(m, ctrl).max(axis=1)
    env = _envelope(level, attack, release, SR / ctrl)
    over = _db(env) - threshold_db
    if knee_db > 0:
        gr = np.where(over <= -knee_db / 2, 0.0,
             np.where(over >= knee_db / 2, over * (1 - 1 / ratio),
                      (1 - 1 / ratio) * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    else:
        gr = np.maximum(over, 0) * (1 - 1 / ratio)
    gain_db = -gr + makeup_db
    t = np.arange(n) / ctrl
    g = 10 ** (np.interp(t, np.arange(m) + 0.5, gain_db) / 20)
    y = x * g[:, None]
    return _f32(mix * y + (1 - mix) * x)


def duck(x, key=None, times=None, depth_db=-8.0, attack=0.005, release=0.25, shape=2.0,
         offset=0.0, period=None):
    """Sidechain ducking ('pumping'). Either from a key signal (e.g. the kick stem) or from a
    list of trigger times in seconds. depth_db = gain at the bottom of each duck.
    Trigger times count from `offset` seconds into x and, with period=, repeat every period
    seconds; a Score stem sets both, so times are score time: s.t(bar, beat)."""
    x = _f32(x)
    n = len(x)
    if times is not None:
        times = [offset + t for t in times]
        if period:
            k0, k1 = -int(np.ceil(offset / period)) - 1, int(np.ceil(n / SR / period)) + 1
            times = [t + k * period for t in times for k in range(k0, k1 + 1)]
        env = np.zeros(n, np.float32)
        a, r = int(attack * SR), int(release * SR)
        curve = np.concatenate([np.linspace(0, 1, max(1, a)), (1 - np.linspace(0, 1, max(1, r))) ** shape])
        for t in times:
            i = int(np.floor(t * SR))
            if i >= n or i + len(curve) <= 0:
                continue
            j = min(n, i + len(curve))
            s = max(0, -i)                  # a duck that started before the buffer: its tail
            env[i + s:j] = np.maximum(env[i + s:j], curve[s: j - i])
    else:
        k = np.abs(key).max(axis=1) if key.ndim == 2 else np.abs(key)
        k = maximum_filter1d(k, size=int(0.01 * SR))
        env = _envelope(k[::32], attack, release, SR / 32)
        env = np.interp(np.arange(n) / 32, np.arange(len(env)), env)
        env = np.clip(env / (env.max() + 1e-9), 0, 1)
    g = 10 ** (depth_db * env / 20)
    return _f32(x * g[:, None])


def gate(x, threshold_db=-50.0, attack=0.002, release=0.08, floor_db=-80.0):
    x = _f32(x)
    det = np.abs(x).max(axis=1)
    m = len(det) // 32 + 1
    lev = np.zeros(m * 32, np.float32)
    lev[:len(det)] = det
    env = _envelope(lev.reshape(m, 32).max(axis=1), attack, release, SR / 32)
    open_ = (_db(env) > threshold_db).astype(np.float32)
    open_ = _envelope(open_, attack, release, SR / 32)
    g = 10 ** ((1 - open_) * floor_db / 20)
    g = np.interp(np.arange(len(x)) / 32, np.arange(m), g)
    return _f32(x * g[:, None])


# ------------------------------------------------------------------ saturation / amps

def _oversample(fn, x, factor=4):
    up = resample_poly(x, factor, 1, axis=0)
    return _f32(resample_poly(fn(up), 1, factor, axis=0)[: len(x)])


def distortion(x, drive=6.0, kind="tanh", tone=6000.0, mix=1.0, bias=0.0):
    """kind: tanh (smooth), tube (asymmetric, even harmonics), hard (clip), fuzz (squared-off),
    fold (wavefolder). drive is a linear pre-gain; output is level-matched roughly."""
    x = _f32(x)

    def shape(s):
        s = s * drive + bias
        if kind == "tanh":
            o = np.tanh(s)
        elif kind == "tube":
            o = np.where(s >= 0, np.tanh(s), np.tanh(0.6 * s) / 0.6 * 0.8)
        elif kind == "hard":
            o = np.clip(s, -1, 1)
        elif kind == "fuzz":
            o = np.sign(s) * (1 - np.exp(-np.abs(s) * 3))
        elif kind == "fold":
            o = np.sin(s * np.pi / 2)
        else:
            raise ValueError(kind)
        return o - np.tanh(bias)
    y = _oversample(shape, x)
    if tone:
        y = sosfilt(butter(2, tone, "low", fs=SR, output="sos"), y, axis=0)
    y = y * (np.sqrt((x ** 2).mean()) / (np.sqrt((y ** 2).mean()) + 1e-9))
    return _f32(mix * y + (1 - mix) * x)


AMP_VOICINGS = {
    #            pre-EQ                          drive kind   post-EQ (cabinet-ish)
    "clean":   ([("hp", 90), ("peak", 900, 2, 0.8)], 1.5, "tube", [("lp", 6500), ("peak", 2500, 2, 1)]),
    "crunch":  ([("hp", 110), ("peak", 800, 4, 0.9)], 7.0, "tube", [("lp", 5200), ("peak", 120, 2, 1), ("peak", 2200, 3, 1.2)]),
    "lead":    ([("hp", 140), ("peak", 900, 6, 0.8)], 22.0, "tanh", [("lp", 4800), ("peak", 1800, 4, 1.4), ("peak", 400, -3, 1)]),
    "metal":   ([("hp", 180), ("peak", 1100, 6, 1.0)], 45.0, "hard", [("lp", 5000), ("peak", 90, 3, 1), ("peak", 700, -5, 1.2), ("peak", 2600, 4, 1.4)]),
    "bass":    ([("hp", 35)], 3.0, "tube", [("lp", 3500), ("peak", 700, -3, 1)]),
}


def amp(x, voicing="crunch", gain=1.0, cabinet=True):
    """Guitar/bass amp + cabinet simulation: pre-EQ -> saturation -> speaker-cab EQ."""
    pre, drive, kind, post = AMP_VOICINGS[voicing]
    y = eq(x, pre)
    y = distortion(y, drive=drive * gain, kind=kind, tone=None)
    if cabinet:
        y = eq(y, post + [("hp", 70)])
    return y


def bitcrush(x, bits=8, downsample=1):
    x = _f32(x)
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    if downsample > 1:
        y = np.repeat(y[::downsample], downsample, axis=0)[: len(x)]
    return _f32(y)


def tape(x, saturation=1.5, wow=0.0015, flutter=0.0004, wow_hz=0.6, flutter_hz=7.0, tone=12000.0,
         period=None):
    """Tape/lo-fi: gentle saturation, wow & flutter pitch drift, high roll-off. No added hiss."""
    wow_hz, flutter_hz = loop_rate(wow_hz, period), loop_rate(flutter_hz, period)
    y = distortion(x, drive=saturation, kind="tanh", tone=tone)
    n = len(y)
    t = np.arange(n) / SR
    dev = wow * np.sin(2 * np.pi * wow_hz * t) + flutter * np.sin(2 * np.pi * flutter_hz * t + 1.3)
    pos = np.arange(n) - (dev * SR + wow * SR)
    return _vdelay(y, pos)


# ------------------------------------------------------------------ modulation

def _vdelay(x, pos):
    """Read x at fractional positions pos (per sample), linear interpolation, per channel."""
    idx = np.arange(len(x))
    out = np.empty_like(x)
    for c in range(x.shape[1]):
        out[:, c] = np.interp(pos, idx, x[:, c], left=0.0, right=0.0)
    return out


def chorus(x, rate=0.8, depth_ms=3.0, delay_ms=12.0, voices=2, mix=0.5, spread=1.0, period=None):
    rate = loop_rate(rate, period)
    x = _f32(x)
    n = len(x)
    t = np.arange(n) / SR
    wet = np.zeros_like(x)
    for v in range(voices):
        ph = 2 * np.pi * v / voices
        for c in range(2):
            lfo = np.sin(2 * np.pi * rate * t + ph + c * np.pi / 2 * spread)
            d = (delay_ms + depth_ms * lfo) * SR / 1000
            wet[:, c] += np.interp(np.arange(n) - d, np.arange(n), x[:, c], left=0.0)
    wet /= voices
    return _f32((1 - mix) * x + mix * wet)


def flanger(x, rate=0.25, depth_ms=2.0, delay_ms=1.0, feedback=0.5, mix=0.5, period=None):
    """Feedback is approximated with 3 extra taps at decaying gains (no per-sample loop)."""
    rate = loop_rate(rate, period)
    x = _f32(x)
    n = len(x)
    t = np.arange(n) / SR
    wet = np.zeros_like(x)
    for c in range(2):
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * rate * t + c * 0.4)
        d = (delay_ms + depth_ms * lfo) * SR / 1000
        for k in range(1, 4):
            wet[:, c] += feedback ** (k - 1) * np.interp(np.arange(n) - k * d, np.arange(n), x[:, c], left=0.0)
    wet /= (1 + feedback + feedback ** 2)
    return _f32((1 - mix) * x + mix * wet)


def phaser(x, rate=0.3, stages=6, low=300.0, high=3000.0, feedback=0.0, mix=0.5, block=128, period=None):
    rate = loop_rate(rate, period)
    x = _f32(x)
    n = len(x)
    centers = (np.arange(0, n, block) + block / 2) / SR
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * rate * centers)
    freqs = low * (high / low) ** lfo
    y = np.empty_like(x)
    zis = [np.zeros((2, 2)) for _ in range(stages)]
    for i, f in enumerate(freqs):
        s = slice(i * block, min(n, (i + 1) * block))
        seg = x[s]
        b, a = biquad("allpass", f, 0.6)
        for k in range(stages):
            seg, zis[k] = lfilter(b, a, seg, axis=0, zi=zis[k])
        y[s] = seg
    return _f32((1 - mix) * x + mix * y)


def tremolo(x, rate=5.0, depth=0.5, shape="sine", stereo_phase=0.0, period=None):
    rate = loop_rate(rate, period)
    n = len(x)
    t = np.arange(n) / SR
    out = np.empty_like(_f32(x))
    for c in range(2):
        ph = 2 * np.pi * rate * t + c * stereo_phase
        lfo = 0.5 + 0.5 * (np.sin(ph) if shape == "sine" else np.sign(np.sin(ph)))
        out[:, c] = x[:, c] * (1 - depth * lfo)
    return out


def leslie(x, speed="slow", mix=1.0, period=None):
    """Rotary speaker: horn (doppler + amplitude) and drum (amplitude) at chorale/tremolo speeds."""
    rate = {"slow": 0.8, "fast": 6.7}[speed] if isinstance(speed, str) else speed
    horn_hz, drum_hz = loop_rate(rate, period), loop_rate(rate * 0.85, period)
    x = _f32(x)
    mono = x.mean(axis=1)
    lo = sosfilt(butter(2, 800, "low", fs=SR, output="sos"), mono)
    hi = mono - lo
    n = len(x)
    t = np.arange(n) / SR
    out = np.zeros_like(x)
    for c, ph in enumerate((0.0, np.pi / 2)):
        horn = np.sin(2 * np.pi * horn_hz * t + ph)
        drum = np.sin(2 * np.pi * drum_hz * t + ph + 1.0)
        d = (0.6 + 0.4 * horn) * SR / 1000
        h = np.interp(np.arange(n) - d, np.arange(n), hi, left=0.0) * (0.75 + 0.25 * horn)
        l = lo * (0.85 + 0.15 * drum)
        out[:, c] = h + l
    return _f32((1 - mix) * x + mix * out)


# ------------------------------------------------------------------ space

def delay(x, seconds=0.375, feedback=0.4, mix=0.3, lp=4000.0, pingpong=True):
    from .engine import ping_pong
    if pingpong:
        return _f32(x + ping_pong(x, seconds, feedback, mix, lp))
    out = _f32(x).copy()
    d = int(seconds * SR)
    sos = butter(1, lp, "low", fs=SR, output="sos")
    sig = _f32(x)
    for k in range(1, 12):
        sig = sosfilt(sos, sig, axis=0)
        g = mix * feedback ** (k - 1)
        if g < 1e-3 or k * d >= len(x):
            break
        out[k * d:] += sig[: len(x) - k * d] * g
    return out


def width(x, amount=1.0):
    mid = (x[:, 0] + x[:, 1]) / 2
    side = (x[:, 0] - x[:, 1]) / 2 * amount
    return _f32(np.stack([mid + side, mid - side], axis=1))


def reverse(x):
    return _f32(x[::-1])


REGISTRY = {
    "eq": eq, "sweep": sweep, "compressor": compressor, "duck": duck, "gate": gate,
    "distortion": distortion, "amp": amp, "bitcrush": bitcrush, "tape": tape,
    "chorus": chorus, "flanger": flanger, "phaser": phaser, "tremolo": tremolo, "leslie": leslie,
    "delay": delay, "width": width,
}


def chain(x, steps, stems=None, clock=None):
    """steps: [("amp", {"voicing": "lead"}), ("delay", {...})]. A step's "key" param may name
    another stem (sidechain); `stems` maps names to their raw audio.
    clock={"offset": s, "period": s or None}: where score time 0 sits in x and the loop
    length; given to every effect that takes offset=/period= and doesn't set its own."""
    import inspect
    for name, params in steps:
        if isinstance(params, (list, tuple)):          # e.g. ("eq", [("lp", 5000)])
            x = REGISTRY[name](x, params)
            continue
        p = dict(params or {})
        if isinstance(p.get("key"), str):
            p["key"] = stems[p["key"]]
        if clock:
            takes = inspect.signature(REGISTRY[name]).parameters
            for k, v in clock.items():
                if k in takes:
                    p.setdefault(k, v)
        x = REGISTRY[name](x, **p)
    return _f32(x)
