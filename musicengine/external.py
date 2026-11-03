"""External renderers as per-note backends: sfizz_render (full SFZ) and FluidSynth (GM SoundFont).

Each note is rendered on its own to a WAV and cached on disk, then placed on the score
timeline like any sampled note - so loop wrapping, stem leveling and the shared hall reverb
work exactly as for the Python sampler. FluidSynth runs with its own reverb/chorus off.

Where a tool comes from, in order:
1. an explicit path in MUSICENGINE_SFIZZ_RENDER / MUSICENGINE_FLUIDSYNTH;
2. the program on PATH (sfizz_render, fluidsynth);
3. Windows only: the pinned upstream release zip, downloaded once into LIBRARY/_tools and
   checked against its SHA-256 before it is extracted.
On other systems a missing tool raises ToolMissing with install hints.
"""
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import engine
from .config import TOOLS, NOTE_CACHE
from .engine import SR

# Official release assets of each upstream project, pinned by version and hash.
TOOL_ZIPS = {
    "sfizz_render": dict(
        url="https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-win64.zip",
        sha256="7431cbe9b7f2e71a9ff4b12fbbe82c766dbf75b1eedecca627e7506cb06a9fcc",
        folder="sfizz-1.2.3"),
    "fluidsynth": dict(
        url="https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.1/fluidsynth-v2.6.1-win10-x64-cpp11.zip",
        sha256="fab7a2e4b85675b66970f97a39bbc239729c5e0f237198b5922a6a73cbc8677c",
        folder="fluidsynth-2.6.1"),
}
TOOL_ENV = {"sfizz_render": "MUSICENGINE_SFIZZ_RENDER", "fluidsynth": "MUSICENGINE_FLUIDSYNTH"}
INSTALL_HINTS = {
    "sfizz_render": "install sfizz (https://sfz.tools/sfizz/downloads; e.g. `brew install sfizz` on macOS, "
                    "or build it with -DSFIZZ_RENDER=ON) so that `sfizz_render` is on PATH",
    "fluidsynth": "install FluidSynth (`apt install fluidsynth`, `brew install fluid-synth`, "
                  "https://www.fluidsynth.org) so that `fluidsynth` is on PATH",
}
_MARKER = ".sha256"          # written after a verified extraction
_IS_WINDOWS = os.name == "nt"  # the pinned zips are Windows builds


class ToolMissing(RuntimeError):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(name):
    """Fetch the pinned Windows release zip, verify its hash, extract it. -> path of name.exe"""
    spec = TOOL_ZIPS[name]
    base = TOOLS / spec["folder"]
    marker = base / _MARKER
    if marker.exists() and marker.read_text().strip() == spec["sha256"]:
        found = list(base.rglob(name + ".exe"))
        if found:
            return found[0]
    TOOLS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TOOLS) as td:
        zpath = Path(td) / "dist.zip"
        print(f"[tools] downloading {spec['url']}")
        urllib.request.urlretrieve(spec["url"], zpath)
        got = _sha256(zpath)
        if got != spec["sha256"]:
            raise ToolMissing(f"{name}: downloaded zip has SHA-256 {got}, expected {spec['sha256']}; "
                              f"not extracting it. Install {name} yourself and set {TOOL_ENV[name]}.")
        stage = Path(td) / "x"
        with zipfile.ZipFile(zpath) as z:
            for member in z.namelist():
                target = (stage / member).resolve()
                if not target.is_relative_to(stage.resolve()):
                    raise ToolMissing(f"{name}: zip entry {member!r} points outside the extraction folder")
            z.extractall(stage)
        if base.exists():
            shutil.rmtree(base)
        shutil.move(str(stage), str(base))
    (base / _MARKER).write_text(spec["sha256"])
    found = list(base.rglob(name + ".exe"))
    if not found:
        raise ToolMissing(f"{name}.exe not in {spec['url']}")
    return found[0]


def tool(name):
    """Path to the sfizz_render / fluidsynth executable (see the module docstring for the order)."""
    env = os.environ.get(TOOL_ENV[name])
    if env:
        if Path(env).is_file():
            return Path(env)
        raise ToolMissing(f"{TOOL_ENV[name]}={env} is not a file")
    found = shutil.which(name)
    if found:
        return Path(found)
    if _IS_WINDOWS:
        return _download(name)
    raise ToolMissing(f"{name} was not found on PATH: {INSTALL_HINTS[name]}, or set {TOOL_ENV[name]} "
                      "to its full path.")


_WARNED = set()


def sfizz_available():
    try:
        tool("sfizz_render")
        return True
    except Exception as e:
        if "sfizz_render" not in _WARNED:
            _WARNED.add("sfizz_render")
            print(f"[tools] {e}\n[tools] SFZ programs that need sfizz are played by the built-in reader, "
                  "which ignores filters, LFOs, loop points and CC crossfades.")
        return False


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def write_midi(path, midi, vel127, dur, tail, program=None, drums=False):
    """One-note Standard MIDI File (format 0, 120 bpm, 960 ticks per quarter = 1920/s)."""
    ch = 9 if drums else 0
    tps = 1920
    ev = b""
    if program is not None and not drums:
        ev += _vlq(0) + bytes([0xC0 | ch, program])
    on = int(0.01 * tps)
    off = on + max(1, int(dur * tps))
    end = off + int(tail * tps)
    ev += _vlq(on) + bytes([0x90 | ch, midi, vel127])
    ev += _vlq(off - on) + bytes([0x80 | ch, midi, 0])
    ev += _vlq(end - off) + b"\xff\x2f\x00"
    tempo = _vlq(0) + b"\xff\x51\x03" + (500000).to_bytes(3, "big")
    trk = tempo + ev
    data = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 960) + b"MTrk" + struct.pack(">I", len(trk)) + trk
    Path(path).write_bytes(data)


class ExternalInstrument:
    def __init__(self, name, backend, path, program=None, drums=False, release=1.5, transpose=0,
                 velocity_curve=False):
        self.name, self.backend, self.path = name, backend, path
        self.program, self.drums, self.release = program, drums, release
        self.transpose = transpose      # key shift so note numbers mean sounding pitch
        # True: also scale by engine.velocity_gain, for maps that barely follow velocity
        # (amp_veltrack=40 gives the button accordion ~3 dB from pp to ff)
        self.velocity_curve = velocity_curve

    def render(self, midi, dur, vel=0.7, rng=None, attack=None, release=None, cents=0.0):
        release = self.release if release is None else release
        midi = midi + self.transpose
        v127 = max(1, min(127, int(round(vel * 127 / 8)) * 8 or 1))      # 16 velocity buckets
        dur_q = round(dur, 2)
        key = hashlib.sha1(f"{self.backend}|{self.path}|{self.program}|{self.drums}|{midi}|{v127}|{dur_q}|{release}"
                           .encode()).hexdigest()
        NOTE_CACHE.mkdir(parents=True, exist_ok=True)
        cached = NOTE_CACHE / f"{key}.wav"
        if not cached.exists():
            self._render_to(cached, midi, v127, dur_q, release)
        x, sr = sf.read(cached, dtype="float32", always_2d=True)
        if x.shape[1] == 1:
            x = np.repeat(x, 2, axis=1)
        x = x[:, :2]
        if sr != SR:
            g = np.gcd(SR, sr)
            x = resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
        skip = int(0.01 * SR)                     # the note-on sits 10 ms into the file
        x = x[skip:]
        if cents:                                 # varispeed retune, like the sampler does
            pos = np.arange(0, len(x) - 1, 2 ** (cents / 1200))
            x = np.stack([np.interp(pos, np.arange(len(x)), x[:, c]) for c in range(2)], 1).astype(np.float32)
        n = int((dur + release) * SR)
        x = x[:n]
        if attack:
            a = min(len(x), int(attack * SR))
            x[:a] *= (np.sin(np.linspace(0, np.pi / 2, a)) ** 2)[:, None]
        r = min(len(x), int(release * SR))
        if r:
            x[-r:] *= (np.cos(np.linspace(0, np.pi / 2, r)) ** 2)[:, None]
        if self.velocity_curve:
            x *= engine.velocity_gain(vel)
        return x

    def _render_to(self, out, midi, v127, dur, release):
        with tempfile.TemporaryDirectory() as td:
            mid = os.path.join(td, "n.mid")
            wav = os.path.join(td, "n.wav")
            write_midi(mid, midi, v127, dur, release + 0.5, self.program, self.drums)
            if self.backend == "sfizz":
                cmd = [str(tool("sfizz_render")), "--sfz", self.path, "--midi", mid, "--wav", wav,
                       "--samplerate", str(SR), "--quality", "3"]   # renders until the release dies out
                                                                     # (--use-eot cut tails at note-off)
            else:
                cmd = [str(tool("fluidsynth")), "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.8",
                       "-r", str(SR), "-F", wav, "-T", "wav", self.path, mid]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode or not os.path.exists(wav):
                raise RuntimeError(f"{self.name}: {self.backend} failed: {r.stderr or r.stdout}")
            part = f"{out}.{os.getpid()}.part"        # atomic: a parallel render never reads half a file
            shutil.move(wav, part)
            os.replace(part, out)
