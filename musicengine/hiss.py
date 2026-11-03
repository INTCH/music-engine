"""Measure hiss/crackle: high-band (>6 kHz) level per section and click count.

usage: python -m musicengine hiss <wav>

There is no universal threshold: hats, shakers and cymbals are meant to live above 6 kHz.
Compare against the brief, and against quiet sections where nothing bright is playing;
spikes that land on the rhythmic grid are attacks, not clicks.
"""
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

x, sr = sf.read(sys.argv[1], dtype="float32")
m = x.mean(axis=1)
hf = sosfilt(butter(4, 6000, "high", fs=sr, output="sos"), m)
full = lambda a: 20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-12)
blk = int(sr * 10)
print("10s blocks: total dB / >6kHz dB / ratio")
for i in range(0, len(m) - blk + 1, blk):
    print(f"  {i // sr:4d}s  {full(m[i:i + blk]):6.1f}  {full(hf[i:i + blk]):6.1f}  {full(hf[i:i + blk]) - full(m[i:i + blk]):6.1f}")
# clicks: HF sample spikes far above local HF level
env = np.convolve(np.abs(hf), np.ones(480) / 480, mode="same")
clicks = np.sum((np.abs(hf) > 8 * env + 1e-4))
print(f"overall >6kHz {full(hf):.1f} dB vs total {full(m):.1f} dB; click-like spikes: {clicks}")
