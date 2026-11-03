"""Measure a reference track (a local audio file the user gives) so a brief can say "like this"
in numbers: tempo, key/mode, loudness and dynamics, tonal balance, stereo width, brightness,
density, and where the energy and sections change. No melody is extracted - the reference
lends its sound and shape, never its notes.

    python -m musicengine reference song.mp3 [out.json]     # -> <stem>.reference.json
    python -m musicengine compare render.wav song.reference.json

Reads wav, flac, ogg and mp3 (libsndfile); anything else goes through ffmpeg.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks, resample_poly, stft

from . import loudness
from .mastering import BANDS, band_levels

SR = 48000
NAMES = "C C# D D# E F F# G G# A A# B".split()
# Krumhansl-Kessler key profiles
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load(path):
    """-> stereo float32 at 48 kHz."""
    try:
        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "ref.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), wav],
                           check=True)
            x, sr = sf.read(wav, dtype="float32", always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if sr != SR:
        g = np.gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
    return x


def _onset_envelope(mono, sr=SR, hop=512):
    """Spectral flux (log magnitude, half-wave rectified), one value per hop."""
    f, t, Z = stft(mono, sr, nperseg=2048, noverlap=2048 - hop)
    mag = np.log1p(100 * np.abs(Z[(f > 30) & (f < 8000)]))
    flux = np.maximum(np.diff(mag, axis=1), 0).sum(axis=0)
    flux = flux - uniform_filter1d(flux, 32)
    return np.maximum(flux, 0), sr / hop


def tempo(mono):
    """-> (bpm, confidence 0-1, [alternatives]). Autocorrelation of the onset envelope, weighted
    toward 120 bpm the way listeners are; the half/double candidates are reported too."""
    env, rate = _onset_envelope(mono)
    if env.std() < 1e-9:
        return 0.0, 0.0, []
    env = (env - env.mean()) / env.std()
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    ac /= ac[0] + 1e-9
    lags = np.arange(len(ac))
    lo, hi = int(rate * 60 / 200), int(rate * 60 / 50)
    lag = lags[lo:hi]
    bpm = 60 * rate / lag
    w = np.exp(-0.5 * (np.log2(bpm / 120) / 0.9) ** 2)
    score = ac[lo:hi] * w
    i = int(np.argmax(score))
    best = float(bpm[i])
    # refine with parabolic interpolation on the lag
    if 0 < i < len(score) - 1:
        a, b, c = score[i - 1], score[i], score[i + 1]
        d = 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
        best = float(60 * rate / (lag[i] + d))
    conf = float(np.clip(ac[lo:hi][i] / (np.abs(ac[lo:hi]).max() + 1e-9), 0, 1))
    alts = [round(best / 2, 1), round(best * 2, 1)]
    return round(best, 1), round(conf, 2), [a for a in alts if 40 <= a <= 220]


def chroma_mean(mono):
    f, t, Z = stft(mono, SR, nperseg=8192, noverlap=4096)
    mag = np.abs(Z)
    valid = (f > 55) & (f < 2000)
    pcs = np.round(69 + 12 * np.log2(f[valid] / 440)).astype(int) % 12
    c = np.zeros(12)
    for pc in range(12):
        c[pc] = mag[valid][pcs == pc].sum()
    return c / (c.sum() + 1e-12)


def key(mono):
    """-> (tonic name, 'major'|'minor', confidence, runner-up). Krumhansl-Schmuckler on the mean
    chroma. Modal music (Dorian, Mixolydian...) reads as its nearest major/minor."""
    c = chroma_mean(mono)
    scores = []
    for r in range(12):
        for mode, prof in (("major", _MAJ), ("minor", _MIN)):
            scores.append((float(np.corrcoef(c, np.roll(prof, r))[0, 1]), NAMES[r], mode))
    scores.sort(reverse=True)
    (s1, k1, m1), (s2, k2, m2) = scores[0], scores[1]
    return k1, m1, round(s1 - s2, 3), f"{k2} {m2}"


def _features(x):
    """Per-second features for the section analysis: short-term loudness, centroid, chroma."""
    mono = x.mean(axis=1)
    f, t, Z = stft(mono, SR, nperseg=8192, noverlap=8192 - SR // 4)
    mag = np.abs(Z)
    cen = (f[:, None] * mag).sum(axis=0) / (mag.sum(axis=0) + 1e-12)
    valid = (f > 55) & (f < 2000)
    pcs = np.round(69 + 12 * np.log2(f[valid] / 440)).astype(int) % 12
    chroma = np.stack([mag[valid][pcs == p].sum(axis=0) for p in range(12)])
    chroma /= chroma.sum(axis=0, keepdims=True) + 1e-12
    st = loudness.short_term(x, hop_s=0.25)
    n = min(len(t), len(st))
    return t[:n], st[:n], cen[:n], chroma[:, :n]


def sections(x, min_gap_s=8.0):
    """Section boundaries (seconds) from a checkerboard novelty over loudness, brightness and
    harmony, plus the energy curve (short-term LUFS once per second)."""
    t, st, cen, chroma = _features(x)
    if len(t) < 16:
        return [], [round(float(v), 1) for v in st]
    feat = np.vstack([(st - st.mean()) / (st.std() + 1e-9),
                      (np.log(cen + 1) - np.log(cen + 1).mean()) / (np.log(cen + 1).std() + 1e-9),
                      chroma * 4])
    feat = uniform_filter1d(feat, 4, axis=1)
    fn = feat / (np.linalg.norm(feat, axis=0, keepdims=True) + 1e-9)
    S = fn.T @ fn
    k = 16                                               # 4 s each side at 4 frames/s
    g = np.outer(np.r_[np.ones(k), -np.ones(k)], np.r_[np.ones(k), -np.ones(k)])
    g *= np.outer(np.hanning(2 * k), np.hanning(2 * k))
    nov = np.zeros(len(t))
    for i in range(k, len(t) - k):
        nov[i] = (S[i - k:i + k, i - k:i + k] * g).sum()
    nov = np.maximum(nov, 0)
    if nov.max() <= 0:
        b = []
    else:
        peaks, _ = find_peaks(nov, distance=int(min_gap_s * 4), height=nov.max() * 0.3)
        b = [round(float(t[p]), 1) for p in peaks]
    per_sec = st[::4]
    return b, [round(float(v), 1) for v in per_sec]


def analyze(path):
    x = load(path)
    mono = x.mean(axis=1)
    bpm, conf, alts = tempo(mono)
    k, mode, kconf, runner = key(mono)
    bands = band_levels(x)
    sel = [i for i, c in enumerate(BANDS) if 60 <= c <= 8000]
    tilt = float(np.polyfit(np.log2(np.array(BANDS)[sel]), np.array(bands)[sel], 1)[0])
    L, R = x[:, 0].astype(np.float64), x[:, 1].astype(np.float64)
    mid, side = (L + R) / 2, (L - R) / 2
    corr = float(np.corrcoef(L, R)[0, 1]) if L.std() > 0 and R.std() > 0 else 1.0
    f, t, Z = stft(mono, SR, nperseg=4096)
    mag = np.abs(Z)
    cen = float(((f[:, None] * mag).sum(axis=0) / (mag.sum(axis=0) + 1e-12)).mean())
    env, rate = _onset_envelope(mono)
    pk, _ = find_peaks(env, height=env.mean() + 1.5 * env.std(), distance=max(1, int(rate * 0.07)))
    bounds, energy = sections(x)
    lv = loudness.measure(x)
    return dict(
        file=str(Path(path).name), seconds=round(len(x) / SR, 1),
        tempo=dict(bpm=bpm, confidence=conf, alternatives=alts),
        key=dict(tonic=k, mode=mode, margin=kconf, runner_up=runner),
        loudness=lv,
        bands=[round(v, 2) for v in bands], band_centers_hz=BANDS, tilt_db_per_octave=round(tilt, 2),
        stereo=dict(correlation=round(corr, 3),
                    side_to_mid_db=round(float(10 * np.log10((side ** 2).mean() / ((mid ** 2).mean() + 1e-20)
                                                             + 1e-20)), 1)),
        centroid_hz=round(cen), onsets_per_second=round(len(pk) / (len(x) / SR), 2),
        sections_s=bounds, energy_lufs_per_s=energy,
        notes="Key and tempo are estimates; modal music reads as its nearest major/minor, and "
              "the tempo may be half or double (see alternatives). No melody is extracted.")


COMPARE = [("tempo bpm", lambda d: d["tempo"]["bpm"]), ("integrated LUFS", lambda d: d["loudness"]["lufs"]),
           ("LRA LU", lambda d: d["loudness"]["lra"]), ("true peak dBTP", lambda d: d["loudness"]["true_peak_db"]),
           ("PLR dB", lambda d: d["loudness"]["plr"]), ("tilt dB/oct", lambda d: d["tilt_db_per_octave"]),
           ("centroid Hz", lambda d: d["centroid_hz"]), ("onsets/s", lambda d: d["onsets_per_second"]),
           ("L/R correlation", lambda d: d["stereo"]["correlation"]),
           ("side/mid dB", lambda d: d["stereo"]["side_to_mid_db"])]


def compare(render_path, ref):
    """-> rows (name, render, reference, delta) plus per-band balance deltas."""
    if isinstance(ref, (str, Path)):
        with open(ref, encoding="utf-8") as fh:
            ref = json.load(fh)
    me = analyze(render_path)
    rows = [(n, get(me), get(ref), round(get(me) - get(ref), 2)) for n, get in COMPARE]
    bands = [(c, round(a - b, 1)) for c, a, b in zip(BANDS, me["bands"], ref["bands"])]
    return dict(rows=rows, band_delta_db=bands, render=me, reference_key=ref["key"], render_key=me["key"])


def _hz(c):
    return f"{c / 1000:g}k" if c >= 1000 else f"{c:g}"


def main(argv):
    if argv[0] == "compare":
        r = compare(argv[1], argv[2])
        print(f"{'':18s} {'render':>9s} {'reference':>10s} {'delta':>8s}")
        for n, a, b, d in r["rows"]:
            print(f"{n:18s} {a:9.2f} {b:10.2f} {d:+8.2f}")
        print("key: render {tonic} {mode}".format(**r["render_key"]),
              "/ reference {tonic} {mode}".format(**r["reference_key"]))
        print("band balance, render - reference (dB):",
              "  ".join(f"{_hz(c)} {d:+.1f}" for c, d in r["band_delta_db"]))
        return
    path = argv[0]
    out = argv[1] if len(argv) > 1 else f"{Path(path).stem}.reference.json"
    d = analyze(path)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    print(json.dumps({k: v for k, v in d.items() if k not in ("energy_lufs_per_s", "bands", "band_centers_hz")},
                     indent=1))
    print(f"-> {out}")
