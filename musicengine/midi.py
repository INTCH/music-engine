"""Standard MIDI File import/export, plus a General MIDI map onto the CC0/synth catalog.

    from musicengine import midi
    midi.export_score(score, "song.mid")              # also: Score.render(..., midi=True)
    song = midi.read("song.mid")                      # -> Song(tempo, notes, tracks)
    midi.render_midi("song.mid", "out/song", drums="808", overrides={"Piano": "synth/e-piano"})

Any MIDI file from a DAW, notation program or the web can be played by this engine's
instruments, so arrangements can be made elsewhere and rendered here.
"""
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------------ GM program -> instrument
GM_PROGRAMS = [
    # 0-7 pianos
    "piano", "piano", "piano", "freepats-old-piano-fb/pianofb-20200401", "synth/e-piano",
    "freepats-fm-piano1/fm-piano1-20190916", "vcsl/chordophones-zithers-harpsichord-french-sustains", "synth/clav",
    # 8-15 chromatic percussion
    "synth/celesta", "vcsl/idiophones-struck-idiophones-glockenspiel", "synth/music-box", "vibes", "marimba",
    "vcsl/idiophones-struck-idiophones-xylophone-medium-mallets", "freepats-tubular-bells1/tubularbells-20241130",
    "synth/hammered-dulcimer",
    # 16-23 organs
    "synth/organ-jazz", "synth/organ-reggae", "synth/organ-rock", "organ_loud",
    "vcsl/aerophones-edge-blown-aerophones-renaissance-organ-8", "freepats-button-accordion-hn/preset-button-accordion-hn-tuned",
    "vcsl/aerophones-free-aerophones-harmonica-hohner-special20-c-sustains-normal",
    "freepats-button-accordion-hn/preset-button-accordion-hn-tuned",
    # 24-31 guitars
    "freepats-spanish-classical-guitar/spanishclassicalguitar-20190618", "karoryfer-shinyguitar/acoustic",
    "freepats-electric-guitar-fsbs-jazz/eguitarfsbs-jazz-bridge-20260807", "guitar_clean", "guitar_clean",
    "freepats-electric-guitar-fsbs-dist1/eguitarfsbs-dist1-bridge-20220911",
    "freepats-electric-guitar-fsbs-dist2/eguitarfsbs-dist2-bridge-20220911", "synth/glass-harmonica",
    # 32-39 basses
    "dsmolken-double-bass/d-smolken-rubner-bass-pizz", "freepats-electric-bass-yr/fingerbassyr-20190930",
    "freepats-electric-bass-yr/pickedbassyr-20190930", "freepats-electric-bass-yr/fingerbassyr-20190930",
    "freepats-electric-bass-yr/pickedbassyr-20190930", "freepats-electric-bass-yr/pickedbassyr-20190930",
    "synth/synth-bass", "synth/acid-bass",
    # 40-47 strings
    "solo_violin", "violas", "celli", "basses", "violins_trem", "vsco/strings-violin-section-pizz", "harp",
    "freepats-timpani/timpani-20240809",
    # 48-55 ensembles
    "violins", "violins", "synth/synth-strings", "synth/warm-pad", "synth/choir-aah", "synth/choir-ooh",
    "synth/voice-solo-ooh", "synth/synth-brass",
    # 56-63 brass
    "trumpet", "trombone", "tuba", "vsco/brass-trumpet-harmonm-sus", "horns", "horns", "synth/synth-brass", "synth/synth-brass",
    # 64-71 reeds
    "karoryfer-weresax/alto-map-forte-dynamic", "karoryfer-weresax/alto-map-forte-dynamic",
    "vcsl/aerophones-reed-aerophones-tenor-saxophone-vibrato", "vcsl/aerophones-reed-aerophones-tenor-saxophone-vibrato",
    "oboe", "oboe", "vsco/woodwinds-bassoon-sus", "clarinet",
    # 72-79 pipes
    "vsco/woodwinds-piccolo-sus", "flute", "vcsl/aerophones-edge-blown-aerophones-baroque-alto-recorder-sustain",
    "synth/pan-flute", "synth/ocarina-synth", "synth/shakuhachi", "synth/whistle", "freepats-ocarina1/ocarina-20241002",
    # 80-87 leads
    "synth/square-lead", "synth/saw-lead", "freepats-synth-calliope/synthcalliope-20200512", "synth/pan-flute",
    "synth/saw-lead", "synth/voice-solo-aah", "freepats-synth-fifths/synthfifths-20200519",
    "freepats-synth-bass-lead/synthbasslead-20200522",
    # 88-95 pads
    "freepats-new-age/newage-20190730", "synth/warm-pad", "synth/supersaw", "freepats-synth-pad-choir/synthpadchoir-20200516",
    "freepats-synth-pad-bowed/synthpadbowed-20190719", "synth/glass-pad", "synth/glass-pad", "freepats-sweep-pad/sweeppad-20190813",
    # 96-103 synth fx
    "synth/glass-pad", "freepats-synth-soundtrack/synthsoundtrack-20200521", "freepats-synth-crystal/synthcrystal-20190812",
    "synth/warm-pad", "synth/glass-pad", "freepats-synth-goblins/synthgoblins-20200612", "synth/glass-pad",
    "freepats-synth-scifi/synthscifi-20200517",
    # 104-111 ethnic
    "synth/sitar", "ganjo/ganjo", "synth/shamisen", "synth/koto", "vcsl/idiophones-plucked-idiophones-kalimba-tanzania",
    "freepats-bagpipe/bagpipe-20260806", "solo_violin", "synth/duduk",
    # 112-119 percussive
    "synth/music-box", "synth/fm-bell", "jlearman-steeldrum/jsteeldrum", "synth/fm-bell",
    "freepats-timpani/timpani-20240809", "freepats-timpani/timpani-20240809", "synth/sub-bass", "synth/glass-pad",
    # 120-127 sound effects (no CC0 equivalents worth having; neutral pad)
    "synth/glass-pad", "synth/glass-pad", "synth/glass-pad", "synth/glass-pad",
    "synth/glass-pad", "synth/glass-pad", "synth/glass-pad", "synth/glass-pad",
]
assert len(GM_PROGRAMS) == 128

# GM drum keys -> (role used to pick a hit from a kit)
GM_DRUMS = {35: "kick", 36: "kick", 37: "rim", 38: "snare", 39: "clap", 40: "snare", 41: "tom-low", 42: "hat-closed",
            43: "tom-low", 44: "hat-pedal", 45: "tom-mid", 46: "hat-open", 47: "tom-mid", 48: "tom-high", 49: "crash",
            50: "tom-high", 51: "ride", 52: "crash", 53: "ride", 54: "tambourine", 55: "crash", 56: "cowbell",
            57: "crash", 59: "ride", 60: "bongo", 61: "bongo", 62: "conga", 63: "conga", 64: "conga", 69: "shaker",
            70: "shaker", 75: "clave", 76: "woodblock", 77: "woodblock"}

# role -> (kit instrument, filename glob) per drum style
DRUM_KITS = {
    "808": {"kick": ("synth/drum-machine-808", "*kick_*"), "snare": ("synth/drum-machine-808", "*snare*"),
            "clap": ("synth/drum-machine-808", "*clap*"), "rim": ("synth/drum-machine-808", "*rim*"),
            "hat-closed": ("synth/drum-machine-808", "*hat-closed*"), "hat-pedal": ("synth/drum-machine-808", "*hat-closed*"),
            "hat-open": ("synth/drum-machine-808", "*hat-open*"), "crash": ("synth/drum-machine-808", "*cymbal*"),
            "ride": ("synth/drum-machine-808", "*ride*"), "tom-low": ("synth/drum-machine-808", "*tom-low*"),
            "tom-mid": ("synth/drum-machine-808", "*tom-mid*"), "tom-high": ("synth/drum-machine-808", "*tom-high*"),
            "cowbell": ("synth/drum-machine-808", "*cowbell*"), "clave": ("synth/drum-machine-808", "*clave*"),
            "shaker": ("synth/drum-machine-808", "*maracas*"), "tambourine": ("synth/drum-machine-808", "*maracas*"),
            "woodblock": ("synth/drum-machine-808", "*clave*"), "bongo": ("synth/drum-machine-808", "*tom-high*"),
            "conga": ("synth/drum-machine-808", "*tom-mid*")},
    "acoustic": {"kick": ("sonicpi/acoustic-kit", "drum_bass_*"), "snare": ("sonicpi/acoustic-kit", "drum_snare_*"),
                 "clap": ("sonicpi/acoustic-kit", "drum_snare_soft*"), "rim": ("sonicpi/acoustic-kit", "drum_snare_soft*"),
                 "hat-closed": ("sonicpi/acoustic-kit", "drum_cymbal_closed*"), "hat-pedal": ("sonicpi/acoustic-kit", "drum_cymbal_pedal*"),
                 "hat-open": ("sonicpi/acoustic-kit", "drum_cymbal_open*"), "crash": ("sonicpi/acoustic-kit", "drum_cymbal_hard*"),
                 "ride": ("sonicpi/acoustic-kit", "drum_cymbal_soft*"), "tom-low": ("sonicpi/acoustic-kit", "drum_tom_lo_*"),
                 "tom-mid": ("sonicpi/acoustic-kit", "drum_tom_mid_*"), "tom-high": ("sonicpi/acoustic-kit", "drum_tom_hi_*"),
                 "cowbell": ("sonicpi/acoustic-kit", "drum_cowbell*"), "clave": ("synth/drum-machine-808", "*clave*"),
                 "shaker": ("synth/drum-machine-808", "*maracas*"), "tambourine": ("synth/drum-machine-808", "*maracas*"),
                 "woodblock": ("synth/drum-machine-808", "*clave*"), "bongo": ("sonicpi/acoustic-kit", "drum_tom_hi_*"),
                 "conga": ("sonicpi/acoustic-kit", "drum_tom_mid_*")},
}
DRUM_KITS["909"] = {k: (inst.replace("808", "909"), pat) for k, (inst, pat) in DRUM_KITS["808"].items()}

ROLE_NOTE = {"kick": 36, "snare": 38, "clap": 39, "rim": 37, "hat-closed": 42, "hat-pedal": 44, "hat-open": 46,
             "crash": 49, "cymbal": 49, "ride": 51, "tom-low": 45, "tom-mid": 47, "tom-high": 50, "cowbell": 56,
             "clave": 75, "shaker": 70, "maracas": 70, "tamb": 54, "gong": 52, "timpani": 41, "tabla": 60}


def role_of_file(path):
    name = Path(str(path)).stem.lower()
    for key in ("hat-closed", "hat-open", "kick", "bass_drum", "bdrum", "bd_", "snare", "sn_", "clap", "rim", "cymbal",
                "crash", "ride", "tom", "cowbell", "clave", "shaker", "maracas", "tamb", "gong", "timp", "tabla"):
        if key in name:
            return {"bass_drum": "kick", "bdrum": "kick", "bd_": "kick", "sn_": "snare", "timp": "timpani",
                    "crash": "cymbal"}.get(key, key)
    return None


# ------------------------------------------------------------------ writing

def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _track(events, name=None):
    """events: list of (tick, bytes). Returns an MTrk chunk."""
    data = b""
    if name:
        nb = name.encode("utf-8")[:120]
        data += _vlq(0) + b"\xff\x03" + _vlq(len(nb)) + nb
    last = 0
    for tick, msg in sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 != 0x80)):
        data += _vlq(max(0, tick - last)) + msg
        last = tick
    data += _vlq(0) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def export_score(score, path, tpq=480):
    """One track per stem; hits go to channel 10 with GM drum notes guessed from file names."""
    sec_to_tick = lambda s: int(round(s / score.beat * tpq))  # noqa: E731
    tempo = int(round(score.beat * 1_000_000))
    meta = [(0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")), (0, b"\xff\x58\x04" + bytes([score.bpb, 2, 24, 8]))]
    by_stem = {}
    for ev in score.events:
        by_stem.setdefault(ev[1], []).append(ev)
    tracks = [_track(meta, "tempo")]
    for ch_i, (stem, evs) in enumerate(by_stem.items()):
        ch = ch_i % 15
        ch = ch + 1 if ch >= 9 else ch          # skip the drum channel for pitched parts
        out = []
        for ev in evs:
            if ev[0] == "note":
                _, _, inst, t, dur, m, v, _ = ev
                vel = max(1, min(127, int(round(v * 127))))
                out += [(sec_to_tick(t), bytes([0x90 | ch, int(m), vel])),
                        (sec_to_tick(t + dur), bytes([0x80 | ch, int(m), 0]))]
            elif ev[0] == "line":
                for t, dur, m, v, _ in ev[3]:
                    vel = max(1, min(127, int(round(v * 127))))
                    out += [(sec_to_tick(t), bytes([0x90 | ch, int(m), vel])),
                            (sec_to_tick(t + dur), bytes([0x80 | ch, int(m), 0]))]
            elif ev[0] == "hit":
                _, _, p, t, gain = ev
                note = ROLE_NOTE.get(role_of_file(p), 60)
                vel = max(1, min(127, int(round(min(1.0, gain) * 110))))
                out += [(sec_to_tick(t), bytes([0x99, note, vel])), (sec_to_tick(t) + tpq // 8, bytes([0x89, note, 0]))]
        if out:
            tracks.append(_track(out, stem))
    data = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), tpq) + b"".join(tracks)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)
    return path


# ------------------------------------------------------------------ reading

@dataclass
class Note:
    start: float        # seconds
    dur: float
    midi: int
    vel: float          # 0..1
    channel: int
    program: int
    track: int


@dataclass
class Song:
    bpm: float
    beats_per_bar: int
    notes: list = field(default_factory=list)
    track_names: dict = field(default_factory=dict)

    @property
    def length(self):
        return max((n.start + n.dur for n in self.notes), default=0.0)


def read(path):
    data = Path(path).read_bytes()
    if data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    _, fmt, ntrk, div = struct.unpack(">IHHH", data[4:14])
    if div & 0x8000:
        raise ValueError("SMPTE time division is not supported")
    pos = 14
    raw = []            # (tick, track, kind, payload)
    names = {}
    for ti in range(ntrk):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("bad track chunk")
        ln = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        p, end = pos + 8, pos + 8 + ln
        tick, status = 0, 0
        while p < end:
            d = 0
            while True:
                b = data[p]; p += 1
                d = (d << 7) | (b & 0x7F)
                if b < 0x80:
                    break
            tick += d
            b = data[p]
            if b == 0xFF:
                typ, p = data[p + 1], p + 2
                ln2 = 0
                while True:
                    c = data[p]; p += 1
                    ln2 = (ln2 << 7) | (c & 0x7F)
                    if c < 0x80:
                        break
                payload = data[p:p + ln2]; p += ln2
                if typ == 0x51:
                    raw.append((tick, ti, "tempo", int.from_bytes(payload, "big")))
                elif typ == 0x58:
                    raw.append((tick, ti, "timesig", payload[0]))
                elif typ in (0x03, 0x04) and ti not in names:
                    names[ti] = payload.decode("utf-8", "replace")
                continue
            if b in (0xF0, 0xF7):
                p += 1
                ln2 = 0
                while True:
                    c = data[p]; p += 1
                    ln2 = (ln2 << 7) | (c & 0x7F)
                    if c < 0x80:
                        break
                p += ln2
                continue
            if b & 0x80:
                status = b
                p += 1
            kind = status & 0xF0
            ch = status & 0x0F
            nbytes = 1 if kind in (0xC0, 0xD0) else 2
            args = data[p:p + nbytes]; p += nbytes
            if kind == 0x90 and args[1] > 0:
                raw.append((tick, ti, "on", (ch, args[0], args[1])))
            elif kind == 0x80 or (kind == 0x90 and args[1] == 0):
                raw.append((tick, ti, "off", (ch, args[0])))
            elif kind == 0xC0:
                raw.append((tick, ti, "prog", (ch, args[0])))
        pos = end
    raw.sort(key=lambda r: (r[0], {"tempo": 0, "timesig": 0, "prog": 1, "off": 2, "on": 3}[r[2]]))
    # tick -> seconds through the tempo map
    tempo, last_tick, last_sec = 500000, 0, 0.0
    first_tempo, bpb = None, 4
    programs = {}
    open_notes = {}
    notes = []
    for tick, ti, kind, val in raw:
        sec = last_sec + (tick - last_tick) * tempo / 1e6 / div
        last_tick, last_sec = tick, sec
        if kind == "tempo":
            tempo = val
            first_tempo = first_tempo or val
        elif kind == "timesig":
            bpb = val
        elif kind == "prog":
            programs[(ti, val[0])] = val[1]
        elif kind == "on":
            ch, m, v = val
            open_notes.setdefault((ti, ch, m), []).append((sec, v, programs.get((ti, ch), 0)))
        elif kind == "off":
            ch, m = val
            stack = open_notes.get((ti, ch, m))
            if stack:
                s, v, prog = stack.pop(0)
                notes.append(Note(s, max(0.02, sec - s), m, v / 127, ch, prog, ti))
    return Song(bpm=60e6 / (first_tempo or 500000), beats_per_bar=bpb, notes=sorted(notes, key=lambda n: n.start),
                track_names=names)


def render_midi(path, out_base, drums="acoustic", overrides=None, loop=False, levels=None, reverb=0.3, seed=1,
                allow_synth=False, **render_kw):
    """Render a MIDI file with catalog instruments. overrides: {track name | "ch<N>" | "prog<N>": instrument}.
    GM programs that map to a synth are refused unless allow_synth=True: override them.
    Drums (channel 10) use a kit style ("acoustic", "808", "909") or any GM-keyed drum
    instrument name, e.g. "drumkit" (Karoryfer Big Rusty Drums, a real CC0 acoustic kit)."""
    import random
    from . import catalog
    from .score import Score
    song = read(path)
    overrides = overrides or {}
    beat = 60 / song.bpm
    bars = max(1, math.ceil(song.length / (beat * song.beats_per_bar)) + (0 if loop else 1))
    s = Score(bpm=song.bpm, bars=bars, beats_per_bar=song.beats_per_bar, seed=seed, loop=loop,
              allow_synth=allow_synth)
    rng = random.Random(seed)
    stems = {}
    for n in song.notes:
        tname = song.track_names.get(n.track, f"track{n.track}")
        if n.channel == 9:
            stem = "drums"
            if stem not in stems:
                stems[stem] = s.stem(stem, level_db=(levels or {}).get(stem, -20), reverb=0.15)
            if drums not in DRUM_KITS:        # a GM-keyed drum instrument (e.g. "drumkit")
                s.note(stem, drums, 0, n.start / beat, max(n.dur / beat, 0.5), n.midi, n.vel, human=0.0)
                continue
            role = GM_DRUMS.get(n.midi)
            if not role:
                continue
            inst, pat = DRUM_KITS[drums][role]
            files = catalog.kit(inst, pat)
            s.hit(stem, rng.choice(files), 0, n.start / beat, gain=0.3 + 0.9 * n.vel)
            continue
        inst = (overrides.get(tname) or overrides.get(f"ch{n.channel + 1}") or overrides.get(f"prog{n.program}")
                or GM_PROGRAMS[n.program])
        stem = f"{tname}-ch{n.channel + 1}"
        if stem not in stems:
            stems[stem] = s.stem(stem, level_db=(levels or {}).get(stem, -21), reverb=reverb)
        s.note(stem, inst, 0, n.start / beat, n.dur / beat, n.midi, n.vel, human=0.0)
    return s.render(out_base, **render_kw)
