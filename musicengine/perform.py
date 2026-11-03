"""Performance: the part between the notes. Recordings are struck note by note; a player
connects them, shapes each long note and bends a phrase toward its high point. Three tools,
all built from the instrument's own recordings (no synthesis):

- legato: the next note's recording starts *after* its attack and crossfades with the tail
  of the previous one, so a line sings instead of re-articulating every note
- swell: a long note's dynamic changes while it sounds, by crossfading a soft and a loud
  rendering of the same note (the dynamic-layer crossfade sample libraries use), so the
  timbre darkens and brightens with the level instead of a plain volume ramp
- phrase: velocities arch toward the phrase's highest note, the last note tapers, and the
  last few onsets relax slightly (a small ritardando inside the phrase only)

Used through Score.line(...) and Score.note(..., swell=...).
"""
import numpy as np

SR = 48000

# breakpoints (position 0-1 of the note's written length, level 0-1 of its velocity)
SWELLS = {
    "hairpin": [(0.0, 0.8), (0.55, 1.0), (1.0, 0.75)],    # < >  the default for long notes
    "cresc": [(0.0, 0.5), (1.0, 1.0)],
    "dim": [(0.0, 1.0), (1.0, 0.45)],
    "fp": [(0.0, 1.0), (0.08, 0.45), (1.0, 0.55)],        # forte-piano
    "bloom": [(0.0, 0.45), (0.8, 1.0), (1.0, 1.0)],       # late swell into the next note
    "flat": [(0.0, 1.0), (1.0, 1.0)],
}


def _curve(swell, n_note, n_total):
    pts = SWELLS[swell] if isinstance(swell, str) else swell
    pos, lev = zip(*pts)
    t = np.arange(n_total) / max(1, n_note)
    return np.interp(np.minimum(t, 1.0), pos, lev).astype(np.float32)


def render_note(inst, midi, dur, vel, rng, swell=None, **kw):
    """One note; with a swell, a crossfade between a soft and a loud rendering that follows the
    curve. When both renderings use the same recording (a single-layer instrument) the mix is
    linear in amplitude, otherwise equal-power."""
    if not swell:
        return inst.render(midi, dur, vel, rng=rng, **kw)
    pts = SWELLS[swell] if isinstance(swell, str) else swell
    lo_l, hi_l = min(p[1] for p in pts), max(p[1] for p in pts)
    if hi_l - lo_l < 1e-3:
        return inst.render(midi, dur, vel * hi_l, rng=rng, **kw)
    state = rng.getstate()
    soft = inst.render(midi, dur, max(0.05, vel * lo_l), rng=rng, **kw)
    rng.setstate(state)                       # same sample choice where layers allow it
    loud = inst.render(midi, dur, min(1.0, vel * hi_l), rng=rng, **kw)
    n = min(len(soft), len(loud))
    soft, loud = soft[:n], loud[:n]
    w = (_curve(swell, int(dur * SR), n) - lo_l) / (hi_l - lo_l)
    a, b = soft[:, 0], loud[:, 0]
    same = abs(float(np.dot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)) > 0.95
    if same:
        ws, wl = 1 - w, w
    else:
        ws, wl = np.cos(w * np.pi / 2), np.sin(w * np.pi / 2)
    return (soft * ws[:, None] + loud * wl[:, None]).astype(np.float32)


def attack_end(x, max_s=0.25):
    """Seconds until the attack (bow bite, tongue, hammer) has settled into the sustain: past
    the early peak, the first point where the level is back within 1.5 dB of the sustain level
    (the median of 0.3-0.6 s). Capped at max_s."""
    k = int(0.01 * SR)
    env = np.sqrt(np.convolve((x[:int(0.7 * SR)] ** 2).mean(axis=1), np.ones(k) / k, mode="same"))
    if len(env) < int(0.6 * SR) or env.max() <= 0:
        return 0.03
    sus = float(np.median(env[int(0.3 * SR):int(0.6 * SR)]))
    cap = int(max_s * SR)
    pk = int(np.argmax(env[:cap]))
    if env[pk] > sus * 1.19:                    # a bite above the sustain: wait until it settles
        after = np.nonzero(env[pk:cap] <= sus * 1.19)[0]
        return float((pk + after[0]) / SR) if len(after) else max_s
    up = np.nonzero(env[:cap] >= sus / 1.19)[0]   # a slow bow: wait until it has grown into the sustain
    return float(up[0] / SR) if len(up) else max_s


def render_line(inst, items, rng, legato=True, xf=0.07, gap=0.05, settle=0.5):
    """items: [(t, dur, midi, vel, kw), ...] sorted by t, seconds. -> (audio, t0).
    A note whose start is within `gap` of the previous note's written end is joined legato:
    the previous note fades out over `xf` centred on the new onset, and the new note enters
    from past its attack (recorded sustains swell in slowly; that swell is skipped), fading in
    over the same window at the previous note's level and easing to its own over `settle` s.
    A repeated pitch keeps half its attack (players re-articulate a repeated note softly)."""
    parts = []
    nxf = int(xf * SR)
    fade_in = np.sin(np.linspace(0, np.pi / 2, nxf))[:, None]     # equal power: two different
    fade_out = np.cos(np.linspace(0, np.pi / 2, nxf))[:, None]    # notes are uncorrelated
    for i, (t, dur, midi, vel, kw) in enumerate(items):
        kw = dict(kw)
        swell = kw.pop("swell", None)
        nxt = items[i + 1] if i + 1 < len(items) else None
        joined_next = legato and nxt is not None and nxt[0] - (t + dur) < gap
        joined_prev = legato and i > 0 and t - (items[i - 1][0] + items[i - 1][1]) < gap
        start, trim = t, 0.0
        if joined_prev:
            probe_state = rng.getstate()
            probe = inst.render(midi, 0.6, vel, rng=rng, **kw)
            rng.setstate(probe_state)
            trim = min(0.25, max(0.02, attack_end(probe)))
            if midi == items[i - 1][2]:
                trim *= 0.5
            start = t - xf / 2
        if joined_next:
            # hold to the end of the crossfade window, then cut; the fade is applied here
            body = (nxt[0] + xf / 2) - start
            kw["release"] = 0.005
            x = render_note(inst, midi, body + trim, vel, rng, swell=swell, **kw)[int(trim * SR):]
            x = x[:int(body * SR)].copy()
            f = min(len(x), nxf)
            x[len(x) - f:] *= fade_out[nxf - f:]
        else:
            x = render_note(inst, midi, dur + (t - start) + trim, vel, rng, swell=swell, **kw)[int(trim * SR):].copy()
        if joined_prev:
            # separately recorded notes sit at different levels; a player carries the level
            # through a slur, so the new note starts at the previous one's level and eases to
            # its own over `settle` seconds
            prev = parts[-1][1]
            w = int(0.1 * SR)
            a = prev[max(0, len(prev) - nxf - w):len(prev) - nxf]
            b = x[nxf:nxf + w]
            if len(a) and len(b):
                g = float(np.sqrt((a ** 2).mean() / ((b ** 2).mean() + 1e-12)))
                g = min(2.0, max(0.5, g))                         # +-6 dB at most
                n = min(len(x), int(settle * SR))
                ramp = g + (1 - g) * (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n)))
                x[:n] *= ramp[:, None].astype(np.float32)
            f = min(len(x), nxf)
            x[:f] *= fade_in[:f]
        parts.append((start, x))
    end = max(s + len(x) / SR for s, x in parts)
    t0 = min(s for s, _ in parts)
    out = np.zeros((int((end - t0) * SR) + 1, 2), np.float32)
    for s, x in parts:
        i = int(round((s - t0) * SR))
        out[i:i + len(x)] += x[: len(out) - i]
    return out, t0


def phrase(notes, arch=0.14, taper=0.18, rit=0.08, rest=1.0):
    """notes: [(start_beat, beats, midi, vel, opts), ...] in absolute beats, sorted. Splits into
    phrases at rests of `rest` beats or more and shapes each: velocities rise toward the
    highest note and fall after it (+-arch/2), the last note is `taper` softer, and the last
    three onsets drift late by up to `rit` beats (durations follow, so legato stays joined)."""
    out, cur = [], []

    def flush():
        if not cur:
            return
        n = len(cur)
        hi = max(c[2] for c in cur)
        peaks = [i for i, c in enumerate(cur) if c[2] == hi]
        pk = peaks[len(peaks) // 2]
        span = max(pk, n - 1 - pk, 1)
        shaped = []
        for i, (b, d, m, v, o) in enumerate(cur):
            v = v + arch * (1 - abs(i - pk) / span) - arch / 2
            if i == n - 1 and n > 1:
                v *= 1 - taper
            shaped.append([b, d, m, min(1.0, max(0.05, v)), o])
        k = min(3, n - 1)
        shifts = [0.0] * n
        for j in range(k):
            idx = n - k + j
            shifts[idx] = rit * ((j + 1) / k) ** 2
        for i in range(n):
            shaped[i][0] += shifts[i]
            if i + 1 < n:
                shaped[i][1] += shifts[i + 1] - shifts[i]
        out.extend(tuple(s) for s in shaped)
        cur.clear()

    for note in notes:
        if cur and note[0] - (cur[-1][0] + cur[-1][1]) >= rest:
            flush()
        cur.append(note)
    flush()
    return out
