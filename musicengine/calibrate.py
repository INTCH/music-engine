"""Measure sample pitches so root notes are known, not guessed.

Filename conventions disagree between libraries (VSCO names middle C "C3", others "C4";
organ files are just numbered), so every pitched instrument is calibrated when fetched.
"""
import os
import re

import numpy as np

from .engine import SR, load, parse_root


def detect_midi(path):
    """Fundamental of a sample in fractional MIDI (autocorrelation, 25 Hz .. 2.5 kHz)."""
    x, _ = load(path)
    m = x.mean(axis=1)
    seg = m[int(0.15 * SR): int(0.15 * SR) + 16384]
    if len(seg) < 8192:
        seg = m[:16384]
    seg = seg * np.hanning(len(seg))
    f = np.fft.rfft(seg, 2 * len(seg))
    ac = np.fft.irfft(f * np.conj(f))[: len(seg)]
    lo, hi = int(SR / 2500), int(SR / 25)
    if hi >= len(ac):
        hi = len(ac) - 1
    lag = lo + int(np.argmax(ac[lo:hi]))
    for div in (4, 3, 2):          # prefer the shortest strong lag (avoid octave-down errors)
        cand = lag // div
        if cand >= lo:
            w = ac[max(lo, cand - 3): cand + 4]
            if w.max() > 0.85 * ac[lag]:
                lag = max(lo, cand - 3) + int(np.argmax(w))
                break
    return 69 + 12 * np.log2(SR / lag / 440)


def number_of(path):
    m = re.search(r"(\d+)(?:_rr\d+)?\.\w+$", os.path.basename(path))
    return int(m.group(1)) if m else None


def calibrate(files, rule, probes=9):
    """rule 'name'   -> octave offset added to filename notes (multiple of 12)
       rule 'number' -> offset so that root = file number + offset
    Returns dict(offset, agree, probed): agree = share of probes within 0.6 semitone."""
    key = parse_root if rule == "name" else number_of
    usable = [f for f in sorted(files) if key(f) is not None]
    if not usable:
        return dict(offset=None, agree=0.0, probed=0)
    step = max(1, len(usable) // probes)
    picks = usable[::step][:probes]
    diffs = []
    for f in picks:
        try:
            diffs.append(detect_midi(f) - key(f))
        except Exception:
            pass
    if not diffs:
        return dict(offset=None, agree=0.0, probed=0)
    diffs = np.array(diffs)
    if rule == "name":
        cands = [-24, -12, 0, 12, 24]
    else:
        cands = sorted({int(round(d)) for d in diffs})
    scores = [(np.mean(np.abs(diffs - c) < 0.6), c) for c in cands]
    agree, offset = max(scores)
    return dict(offset=int(offset), agree=float(agree), probed=len(diffs))
