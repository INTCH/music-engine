"""Loudness by ITU-R BS.1770-4 / EBU R128: integrated LUFS, short-term loudness, loudness
range (LRA), true peak (4x oversampled) and PLR. Stereo float arrays at 48 kHz.

    from musicengine import loudness
    m = loudness.measure(x)          # {"lufs": -16.0, "lra": 6.1, "true_peak_db": -1.0, "plr": 15.0}
"""
import numpy as np
from scipy.signal import lfilter, resample_poly

SR = 48000

# K-weighting at 48 kHz (BS.1770-4, table 1 and 2): a high shelf for the head, then an RLB high-pass.
_SHELF = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
_RLB = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def _stereo(x):
    x = np.asarray(x, dtype=np.float64)
    return np.stack([x, x], axis=1) if x.ndim == 1 else x


def k_weight(x):
    y = lfilter(*_SHELF, _stereo(x), axis=0)
    return lfilter(*_RLB, y, axis=0)


def _block_power(x, block_s, hop_s):
    """Mean square of the K-weighted signal, summed over channels, per gating block."""
    y = k_weight(x) ** 2
    b, h = int(block_s * SR), int(hop_s * SR)
    if len(y) < b:
        return np.array([y.mean(axis=0).sum()]) if len(y) else np.array([0.0])
    c = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y, axis=0)])
    starts = np.arange(0, len(y) - b + 1, h)
    return ((c[starts + b] - c[starts]) / b).sum(axis=1)


def _lufs(power):
    return -0.691 + 10 * np.log10(np.maximum(power, 1e-20))


def integrated(x):
    """Gated integrated loudness in LUFS (400 ms blocks, 75 % overlap, -70 LUFS absolute gate,
    -10 LU relative gate). -inf-ish (-200) for silence."""
    p = _block_power(x, 0.4, 0.1)
    p = p[_lufs(p) > -70]
    if not len(p):
        return -200.0
    rel = _lufs(p.mean()) - 10
    p = p[_lufs(p) > rel]
    return float(_lufs(p.mean())) if len(p) else -200.0


def short_term(x, hop_s=0.1):
    """Short-term loudness (3 s window) every hop_s seconds, in LUFS."""
    return _lufs(_block_power(x, 3.0, hop_s))


def lra(x):
    """Loudness range (EBU Tech 3342): spread of short-term loudness, 10th to 95th percentile,
    after a -70 LUFS absolute and a -20 LU relative gate."""
    st = short_term(x)
    st = st[st > -70]
    if len(st) < 2:
        return 0.0
    rel = _lufs((10 ** ((st + 0.691) / 10)).mean()) - 20
    st = st[st > rel]
    if len(st) < 2:
        return 0.0
    return float(np.percentile(st, 95) - np.percentile(st, 10))


def oversampled_peak(x, factor=4):
    """Per-sample peak of the 4x oversampled signal over both channels (length len(x))."""
    x = _stereo(x)
    up = np.abs(resample_poly(x, factor, 1, axis=0))
    n = len(x)
    up = up[: n * factor].reshape(n, factor, -1) if len(up) >= n * factor else \
        np.pad(up, ((0, n * factor - len(up)), (0, 0))).reshape(n, factor, -1)
    return up.max(axis=(1, 2))


def true_peak_db(x):
    return float(20 * np.log10(max(oversampled_peak(x).max(), 1e-10)))


def measure(x):
    lufs = integrated(x)
    tp = true_peak_db(x)
    return dict(lufs=round(lufs, 2), lra=round(lra(x), 2), true_peak_db=round(tp, 2), plr=round(tp - lufs, 2))
