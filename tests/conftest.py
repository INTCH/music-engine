"""Two kinds of tests:
- fast, sample-free (default; run by the pre-commit hook and CI)
- `samples`: render real instruments from ~/SoundLibrary; skipped when it isn't there.
  Their golden hashes depend on numpy/scipy versions, so they are local checks, not CI.
"""
import numpy as np
import pytest

from musicengine.config import LIBRARY

SR = 48000


def pytest_collection_modifyitems(config, items):
    if (LIBRARY / "VSCO-2-CE").exists():
        return
    skip = pytest.mark.skip(reason=f"sample library not found at {LIBRARY}")
    for item in items:
        if "samples" in item.keywords:
            item.add_marker(skip)


def sine(freq, seconds, db=-20.0, sr=SR):
    t = np.arange(int(seconds * sr)) / sr
    x = 10 ** (db / 20) * np.sin(2 * np.pi * freq * t)
    return np.stack([x, x], axis=1).astype(np.float32)
