"""Objective checks on a rendered track (no ears needed):
- loudness per section, peak and clipping
- loop seam: level and waveform jump between the last and first samples
- per-bar chroma vs the intended chord (are the samples mapped to the right pitches?)
- a spectrogram/loudness PNG for a visual look

usage: python -m musicengine analyze <wav> <bpm> <beats_per_bar> [expected_pcs_json]

Chroma counts overtones too, so sustained low notes and mallets lower the agreement;
when a bar disagrees, check per stem before changing notes.
"""
import sys
import json

import numpy as np
import soundfile as sf
from scipy.signal import stft

NAMES = "C C# D D# E F F# G G# A A# B".split()


def _db(a):
    return 20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-9)


def seam(x, sr):
    """-> dict(tail_db, head_db, jump, near, ok). The step between the last and the first sample
    against the largest step within 10 ms on either side."""
    w = int(0.05 * sr)
    jump = float(np.abs(x[0] - x[-1]).max())
    steps = np.abs(np.diff(np.concatenate([x[-480:], x[:480]]), axis=0)).max(axis=1)
    near = float(max(steps[:479].max(), steps[480:].max()))
    return dict(tail_db=float(_db(x[-w:])), head_db=float(_db(x[:w])), jump=jump, near=near, ok=jump <= near * 1.2)


def bar_levels(x, sr, bar_s):
    nbar = int(round(len(x) / sr / bar_s))
    return [float(_db(x[int(b * bar_s * sr): int((b + 1) * bar_s * sr)])) for b in range(nbar)]


def bar_chroma(x, sr, bar_s, nbar):
    """-> 12 x nbar mean chroma per bar (60 Hz - 2 kHz, from 0.3 s into each bar)."""
    mono = x.mean(axis=1)
    f, t, Z = stft(mono, sr, nperseg=8192, noverlap=4096)
    mag = np.abs(Z)
    valid = (f > 60) & (f < 2000)
    pcs = np.round(69 + 12 * np.log2(f[valid] / 440)).astype(int) % 12
    chroma = np.zeros((12, mag.shape[1]))
    for pc in range(12):
        chroma[pc] = mag[valid][pcs == pc].sum(axis=0)
    out = np.zeros((12, nbar))
    for b in range(nbar):
        sel = (t >= b * bar_s + 0.3) & (t < (b + 1) * bar_s)
        if sel.any():
            out[:, b] = chroma[:, sel].mean(axis=1)
    return out, (f, t, mag)


def chroma_agreement(chroma, expected):
    """-> (hits, possible, per-bar [(top3, good)]). A bar scores how many of its 3 strongest pitch
    classes belong to the intended chord. Bars past `expected` (a cue's reverb tail) are skipped."""
    hits, rows = 0, []
    nb = min(chroma.shape[1], len(expected))
    for b in range(chroma.shape[1]):
        top = [int(p) for p in np.argsort(chroma[:, b])[::-1][:3]]
        good = sum(p in set(expected[b]) for p in top) if b < nb else None
        hits += good or 0
        rows.append((top, good))
    return hits, 3 * nb, rows


def run(path, bpm, bpb, expected=None, png=True, out=print):
    x, sr = sf.read(path, dtype="float32")
    bar = 60 / bpm * bpb
    nbar = int(round(len(x) / sr / bar))
    clipped = int((np.abs(x) >= 0.999).sum())
    out(f"{path}: {len(x) / sr:.1f}s, {nbar} bars, peak {np.abs(x).max():.3f}, clipped samples {clipped}")
    sm = seam(x, sr)
    out(f"seam (if looped): last50ms {sm['tail_db']:.1f} dB / first50ms {sm['head_db']:.1f} dB, step at seam "
        f"{sm['jump']:.4f} vs max step within 10 ms {sm['near']:.4f} -> {'OK' if sm['ok'] else 'CLICK RISK'}")
    lv = bar_levels(x, sr, bar)
    out("dB per bar: " + " ".join(f"{v:.0f}" for v in lv))
    chroma, (f, t, mag) = bar_chroma(x, sr, bar, nbar)
    res = dict(seconds=len(x) / sr, bars=nbar, peak=float(np.abs(x).max()), clipped=clipped, seam=sm,
               bar_db=lv, chroma_agreement=None)
    if expected:
        hits, possible, rows = chroma_agreement(chroma, expected)
    else:
        rows = [([int(p) for p in np.argsort(chroma[:, b])[::-1][:3]], None) for b in range(nbar)]
    for b, (top, good) in enumerate(rows):
        ok = f" exp {[NAMES[p] for p in expected[b]]} -> {good}/3" if good is not None else ""
        out(f"bar {b:2d} top {[NAMES[p] for p in top]}{ok}")
    if expected:
        res["chroma_agreement"] = hits / possible if possible else None
        res["chroma_bars"] = [g for _, g in rows]
        out(f"chroma agreement: {hits}/{possible} = {hits / possible:.0%}")
    if png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
        ax[0].plot(np.arange(nbar) * bar, lv, drawstyle="steps-post")
        ax[0].set_ylabel("dB / bar")
        ax[0].grid(alpha=0.3)
        ax[1].pcolormesh(t, f[f < 5000], 20 * np.log10(mag[f < 5000] + 1e-6), shading="auto", vmin=-90, vmax=-20)
        ax[1].set_yscale("symlog", linthresh=200)
        ax[1].set_ylabel("Hz")
        ax[1].set_xlabel("s")
        plt.tight_layout()
        plt.savefig(path.replace(".wav", "_analysis.png"), dpi=80)
        plt.close(fig)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0], float(a[1]), int(a[2]), json.loads(open(a[3]).read()) if len(a) > 3 else None)
