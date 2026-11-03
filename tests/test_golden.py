"""Renders with real samples must not change unless someone meant them to. Local only: the
hashes depend on numpy/scipy versions. After an intended change (or an upgrade), regenerate:

    MUSICENGINE_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from musicengine.score import Score

GOLDEN = Path(__file__).with_name("golden.json")


def _render(master, tmp_path):
    s = Score(bpm=96, bars=4, seed=5, genre="orchestral")
    s.stem("strings", level_db=-21, reverb=0.4)
    s.stem("drums", level_db=-20, reverb=0.15, role="percussion")
    for b, root in enumerate([57, 53, 48, 55]):
        s.notes("strings", "violins", b, 0, 4, [root + 12, root + 16, root + 19], vel=0.6)
        s.notes("strings", "celli", b, 0, 4, [root - 12], vel=0.6)
        for q in range(4):
            s.note("drums", "drumkit", b, q, 0.5, 36 if q % 2 == 0 else 38, 0.7, human=0)
    base = str(tmp_path / master)
    s.render(base, ir_seconds=3.0)
    x, _ = sf.read(base + ".wav", dtype="int32")
    return hashlib.sha1(np.ascontiguousarray(x).tobytes()).hexdigest()


@pytest.mark.samples
@pytest.mark.parametrize("master", ["modern"])
def test_render_is_unchanged(master, tmp_path):
    h = _render(master, tmp_path)
    data = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    if os.environ.get("MUSICENGINE_UPDATE_GOLDEN") or master not in data:
        data[master] = h
        GOLDEN.write_text(json.dumps(data, indent=1) + "\n")
        pytest.skip(f"golden hash for {master} written")
    assert h == data[master], "render changed; if intended, regenerate with MUSICENGINE_UPDATE_GOLDEN=1"
