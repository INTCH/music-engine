"""The master: what makes a render sound produced rather than merely mixed.

    low cut 28 Hz -> low end to mono -> genre EQ -> optional reference-match EQ
    -> glue compressor -> true-peak limiter -> gain to a LUFS target (default -16 LUFS, -1 dBTP)

Stems must still sum exactly to the mix (adaptive game music). So the master only uses
linear filters and time-varying gain curves computed from the mix; master_stem() runs the same
filters on a stem and multiplies it by the same curve. Anything nonlinear (saturation,
parallel compression) belongs on the stems, through the genre presets' role chains.
"""
import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import butter, sosfilt

from . import fx, loudness

SR = 48000

# Genre presets. master: EQ bands (fx.eq format), mono_hz, glue compressor. roles: fx chains a
# stem gets when it is declared with stem(..., role=...) on a Score(genre=...).
_PAR_DRUMS = ("compressor", {"threshold_db": -30, "ratio": 6, "attack": 0.002, "release": 0.12, "mix": 0.35})
_BASS_GLUE = ("compressor", {"threshold_db": -24, "ratio": 3, "attack": 0.01, "release": 0.2})
_WARM = ("distortion", {"drive": 1.6, "kind": "tube", "tone": 9000, "mix": 0.25})

PRESETS = {
    "default": dict(eq=[], mono_hz=120, glue=dict(ratio=1.8, pct=80, attack=0.03, release=0.3, max_gr=3.0),
                    roles={"drums": [_PAR_DRUMS], "bass": [_BASS_GLUE]}),
    "orchestral": dict(eq=[("lowshelf", 90, -1.0), ("highshelf", 9000, 1.0)], mono_hz=80,
                       glue=dict(ratio=1.5, pct=90, attack=0.05, release=0.5, max_gr=2.0),
                       roles={"percussion": [("compressor", {"threshold_db": -26, "ratio": 2.5, "attack": 0.01,
                                                             "release": 0.3, "mix": 0.4})]}),
    "ambient": dict(eq=[("highshelf", 10000, 1.0)], mono_hz=80,
                    glue=dict(ratio=1.4, pct=90, attack=0.08, release=0.8, max_gr=1.5), roles={}),
    "cinematic": dict(eq=[("lowshelf", 70, 1.0), ("peak", 350, -1.0, 0.8), ("highshelf", 8000, 1.5)], mono_hz=100,
                      glue=dict(ratio=2.0, pct=80, attack=0.02, release=0.25, max_gr=3.0),
                      roles={"drums": [_PAR_DRUMS], "percussion": [_PAR_DRUMS], "bass": [_BASS_GLUE]}),
    "rock": dict(eq=[("peak", 250, -1.5, 0.9), ("peak", 3000, 1.0, 0.8), ("highshelf", 10000, 1.0)], mono_hz=120,
                 glue=dict(ratio=2.0, pct=70, attack=0.02, release=0.2, max_gr=3.0),
                 roles={"drums": [_PAR_DRUMS, ("distortion", {"drive": 1.4, "kind": "tube", "mix": 0.15})],
                        "bass": [_BASS_GLUE, _WARM], "guitar": [("eq", [("hp", 90), ("peak", 400, -2, 1.0)])]}),
    "pop": dict(eq=[("lowshelf", 80, 1.0), ("peak", 300, -1.5, 0.9), ("highshelf", 10000, 2.0)], mono_hz=120,
                glue=dict(ratio=2.0, pct=70, attack=0.02, release=0.2, max_gr=3.0),
                roles={"drums": [_PAR_DRUMS], "bass": [_BASS_GLUE, _WARM], "vocal": [_BASS_GLUE]}),
    "electronic": dict(eq=[("lowshelf", 60, 1.5), ("peak", 300, -1.5, 0.9), ("highshelf", 11000, 1.5)], mono_hz=150,
                       glue=dict(ratio=2.5, pct=65, attack=0.01, release=0.15, max_gr=3.5),
                       roles={"drums": [_PAR_DRUMS], "bass": [_BASS_GLUE, _WARM]}),
    "lofi": dict(eq=[("lowshelf", 120, 1.0), ("highshelf", 7000, -2.5), ("lp", 14000)], mono_hz=120,
                 glue=dict(ratio=2.0, pct=70, attack=0.03, release=0.3, max_gr=3.0),
                 roles={"drums": [_PAR_DRUMS, ("tape", {"saturation": 1.8})], "bass": [_BASS_GLUE],
                        "keys": [("tape", {"saturation": 1.4})]}),
    "jazz": dict(eq=[("highshelf", 9000, 0.5)], mono_hz=90,
                 glue=dict(ratio=1.5, pct=85, attack=0.03, release=0.4, max_gr=1.5), roles={}),
    "folk": dict(eq=[("peak", 250, -1.0, 0.9), ("highshelf", 9000, 1.0)], mono_hz=100,
                 glue=dict(ratio=1.6, pct=80, attack=0.03, release=0.3, max_gr=2.0), roles={}),
    "chiptune": dict(eq=[], mono_hz=120, glue=dict(ratio=2.0, pct=70, attack=0.01, release=0.15, max_gr=2.5),
                     roles={}),
    "world": dict(eq=[("highshelf", 9000, 1.0)], mono_hz=100,
                  glue=dict(ratio=1.6, pct=80, attack=0.03, release=0.3, max_gr=2.0),
                  roles={"percussion": [_PAR_DRUMS]}),
}
ALIASES = {"house": "electronic", "techno": "electronic", "dnb": "electronic", "synthwave": "electronic",
           "trailer": "cinematic", "hybrid": "cinematic", "metal": "rock", "funk": "pop", "reggae": "pop",
           "hiphop": "lofi", "lo-fi": "lofi", "celtic": "folk", "latin": "world", "choral": "orchestral",
           "horror": "ambient", "drone": "ambient"}


def preset(genre):
    g = (genre or "default").lower()
    g = ALIASES.get(g, g)
    if g not in PRESETS:
        raise ValueError(f"unknown genre preset {genre!r}; known: {sorted(PRESETS) + sorted(ALIASES)}")
    return PRESETS[g]


def role_fx(genre, role):
    """The fx chain a stem with this role gets under this genre ([] when none)."""
    return list(preset(genre)["roles"].get(role, [])) if role else []


# ------------------------------------------------------------------ reference match

BANDS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def band_levels(x):
    """Octave-band levels in dB relative to the total (the spectral balance), averaged over the
    whole signal, mono sum. Used to match a mix to a reference track."""
    from scipy.signal import welch
    mono = np.asarray(x, dtype=np.float64)
    mono = mono.mean(axis=1) if mono.ndim == 2 else mono
    f, p = welch(mono, SR, nperseg=8192)
    total = p.sum() + 1e-20
    out = []
    for c in BANDS:
        sel = (f >= c / np.sqrt(2)) & (f < c * np.sqrt(2))
        out.append(float(10 * np.log10(p[sel].sum() / total + 1e-20)))
    return out


def match_eq(x, ref_bands, amount=0.7, cap_db=4.0):
    """Peak-EQ bands that move x's octave balance toward ref_bands. Smoothed across neighbours
    and capped, so it nudges the tone rather than copying a curve."""
    d = np.array(ref_bands) - np.array(band_levels(x))
    d = d - np.median(d)                                  # balance only, not level
    d = np.convolve(np.pad(d, 1, mode="edge"), [0.25, 0.5, 0.25], mode="valid")
    d = np.clip(d * amount, -cap_db, cap_db)
    return [("peak", c, round(float(g), 2), 1.4) for c, g in zip(BANDS, d) if abs(g) >= 0.25 and c < 20000]


# ------------------------------------------------------------------ linear part

def _linear(x, cfg):
    y = sosfilt(butter(2, 28, "high", fs=SR, output="sos"), x, axis=0)
    if cfg.get("mono_hz"):
        mid = (y[:, 0] + y[:, 1]) / 2
        side = (y[:, 0] - y[:, 1]) / 2
        side = sosfilt(butter(2, cfg["mono_hz"], "high", fs=SR, output="sos"), side)
        y = np.stack([mid + side, mid - side], axis=1)
    bands = list(cfg.get("eq", [])) + list(cfg.get("match", []))
    if bands:
        y = fx.eq(y, bands)
    return np.asarray(y, dtype=np.float32)


# ------------------------------------------------------------------ gain curves

def _glue_curve(y, region, ratio, pct, attack, release, max_gr, knee_db=6.0, ctrl=64):
    """Gain curve of a slow bus compressor whose threshold sits at the pct-th percentile of the
    track's own active level, so it only leans on the loudest passages, by at most max_gr dB."""
    mono = (y[:, 0] + y[:, 1]) / 2
    n = len(mono)
    m = (n + ctrl - 1) // ctrl
    pw = np.zeros(m * ctrl, np.float64)
    pw[:n] = mono ** 2
    level = pw.reshape(m, ctrl).mean(axis=1)
    env = fx._envelope(level.astype(np.float32), attack, release, SR / ctrl)
    db = 10 * np.log10(np.maximum(env, 1e-12))
    a, b = region[0] // ctrl, max(region[0] // ctrl + 1, region[1] // ctrl)
    act = db[a:b][db[a:b] > db[a:b].max() - 40]
    thr = np.percentile(act, pct) if len(act) else db.max()
    over = db - thr
    gr = np.where(over <= -knee_db / 2, 0.0,
                  np.where(over >= knee_db / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    gr = np.minimum(gr, max_gr)
    g = 10 ** (-np.interp(np.arange(n) / ctrl, np.arange(m) + 0.5, gr) / 20)
    return g.astype(np.float32), float(gr[a:b].max()) if b > a else 0.0


def _limiter_curve(y, ceiling_db, lookahead_s=0.005, release_s=0.08, block=48):
    """Look-ahead true-peak limiter gain: the oversampled peak decides, the gain falls before the
    peak (min-hold + smoothing over the look-ahead) and recovers exponentially."""
    c = 10 ** (ceiling_db / 20)
    need = np.minimum(1.0, c / (loudness.oversampled_peak(y) + 1e-9))
    win = int(lookahead_s * SR)
    g = uniform_filter1d(minimum_filter1d(need, 2 * win + 1), win)
    n = len(g)
    m = (n + block - 1) // block
    gb = np.ones(m * block)
    gb[:n] = g
    gb = gb.reshape(m, block).min(axis=1)
    rel = 1 - np.exp(-1.0 / (release_s * SR / block))
    e, out = 1.0, np.empty(m)
    for i, v in enumerate(gb):
        e = v if v < e else e + (1 - e) * rel
        out[i] = e
    smooth = np.interp(np.arange(n) / block, np.arange(m), out)
    return np.minimum(smooth, need).astype(np.float32)


SHORT_CUE_S = 10.0          # below this a render is a stinger: integrated loudness reads hot


def master(x, target_lufs=-16.0, ceiling_dbtp=-1.0, region=None, genre=None, match=None, gains=None,
           glue=True):
    """-> (mastered, info). region=(start, end): the part loudness is measured on (a loop's
    cycle); the processing runs over everything so a loop cut from it stays seamless.
    match: octave-band balance of a reference (reference.json "bands") to lean toward.
    gains: receives what master_stem() needs to process stems identically.
    glue=False: no bus compressor. Used for stem renders, where the mix's compression would be
    baked into every stem and a layer heard alone would pump on hits it no longer contains.
    Stingers (region shorter than SHORT_CUE_S) aim 2 LU below the target."""
    p = preset(genre)
    cfg = dict(eq=p["eq"], mono_hz=p["mono_hz"])
    a, b = region or (0, len(x))
    if (b - a) / SR < SHORT_CUE_S:
        target_lufs -= 2.0
    xl = _linear(x, cfg)
    if match:
        cfg["match"] = match_eq(xl[a:b], match)
        xl = _linear(x, cfg)
    lufs0 = loudness.integrated(xl[a:b])
    silent = lufs0 < -150
    # the glue compressor sees the mix at a fixed level, so how hard it works doesn't depend on
    # the loudness iteration below; only the gain into the limiter is iterated
    pre = 1.0 if silent else 10 ** ((target_lufs - lufs0) / 20)
    if glue:
        g_curve, glue_gr = _glue_curve(xl * pre, (a, b), **p["glue"])
    else:
        g_curve, glue_gr = np.ones(len(xl), np.float32), 0.0
    y = xl * (pre * g_curve)[:, None]
    post = 1.0
    for _ in range(8):
        lim = _limiter_curve(y * post, ceiling_dbtp)
        curve = pre * g_curve * post * lim
        out = (xl * curve[:, None]).astype(np.float32)
        err = 0.0 if silent else target_lufs - loudness.integrated(out[a:b])
        if abs(err) < 0.05:
            break
        post *= 10 ** (err / 20)
    lim_gr = float(-20 * np.log10(max(lim[a:b].min(), 1e-9)))
    if gains is not None:
        gains.update(mode="modern", cfg=cfg, curve=curve)
    info = dict(mode="modern", genre=genre or "default", target_lufs=target_lufs, ceiling_dbtp=ceiling_dbtp,
                glue=bool(glue), glue_max_gr_db=round(glue_gr, 2), limiter_max_gr_db=round(lim_gr, 2),
                match_eq=cfg.get("match", []))
    return out, info


def master_stem(y, gains):
    """Run a stem through the mix's master exactly (same filters, same gain curve)."""
    return (_linear(y, gains["cfg"]) * gains["curve"][:, None]).astype(np.float32)
