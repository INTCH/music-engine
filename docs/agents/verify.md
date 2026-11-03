# Verifying a render (you cannot listen; measure instead)

Run after every render, and fix problems before showing anything:

```
python -m musicengine verify music/my_track/plan.json music/my_track/out/my_track.wav   # exit 1 on FAIL
python -m musicengine hiss music/my_track/out/my_track.wav
```

verify reads the chords and dynamic marks from plan.json, the master settings and loudness
from render.json, and writes `<render>.verify.json` plus an analysis PNG. It checks licenses
and recordings-only (synthesized sources pass only with a plan `"synth"` reason), length,
clipping, the loop seam, LUFS on target, true peak (wav and ogg), limiter load, chroma vs
chords, the section levels against the planned dynamics, and, with a reference, the
differences to it.

- **FAIL** blocks showing the render. Fix the cause and re-render.
- **WARN** needs a look and a sentence in the report.
- **INFO** is context.

Without a plan (a MIDI render, a quick sketch), use the parts directly:
`python -m musicengine analyze <wav> <bpm> <beats_per_bar> [chords.json]` and
`python -m musicengine loudness <wav>`.

## The gates

| Check | Status on failure | Good | Investigate |
|---|---|---|---|
| licenses / recordings only | FAIL | only `CC0-1.0`, `Unlicense` (plus `Synthesized` with a plan reason) | anything else: a synth or a non-CC0 source slipped in |
| clipping | FAIL | 0 clipped samples | any |
| length | FAIL | loop: exactly the planned bars; one-shot: bars + tail | wrong bar count or tempo |
| loop seam | FAIL | `ok` | the seam step is larger than the steps around it |
| loudness | FAIL | target ±1 LU (−16 LUFS default) | off: check render.json `master` |
| true peak (wav) | FAIL | ≤ ceiling (−1 dBTP default) + 0.1 | over: lower the loudest stem |
| true peak (ogg) | WARN | within 0.5 dB of the ceiling | higher: Vorbis overshoot, consider `ceiling_dbtp=-1.5` |
| limiter | WARN | ≤ ~3 dB gain reduction | higher: lower or compress the loudest stem (usually drums) |
| chroma vs chords | WARN | ≥ `verify.chroma_min` (default 0.8; 0.85–0.9 for plain chord music) | below: check each stem before changing notes |
| dynamics arc | WARN | rank correlation ≥ `verify.dynamics_min_rho` (default 0.6) | sections do not get louder/softer as planned |
| loop energy | WARN | first and last section within 6 dB | the loop restarts at a different energy |
| reference | INFO | differences you can explain | — |

Other numbers worth reading:

| Number | Good | Investigate |
|---|---|---|
| scale fit (modal/world music) | 65–90% of energy inside the scale | lower: a wrong pitch or a mis-mapped sample |
| level per bar | follows the planned arc | flat where it should build, or a peak in the wrong place |
| >6 kHz energy (`hiss`) | suits the genre (hats and shakers are bright) | in quiet sections with nothing bright playing: hiss |
| click-like spikes (`hiss`) | all on the rhythmic grid (16ths or swing) | off-grid spikes: clicks |

Chroma counts overtones too. The 3rd harmonic of F# reads as C#, and low sustains, mallets,
bells and voices all lower the agreement. A bar that disagrees is a lead, not proof of an
error.

## Per-stem diagnosis

When a bar looks wrong, look at what each stem contributes in that bar. Call
`s.place_all()`, then take the FFT of `s.mix.stems[name][pre + bar*len : …]` and compare
the loudest peaks with the notes that were asked for. This finds:
- a sustain held into the next chord (fix: place sustains with `chord_run`)
- an instrument mapped an octave off
- a synth partial that falls outside the key

## New or unusual instruments

Before relying on an instrument, run `python -m musicengine check <name>`:
- `OK` everywhere: fine.
- `OCTAVE?` on organs with 16' stops, on bells or on low notes: usually the detector, not
  the instrument. Confirm with chroma in a real render.
- `WRONG` showing a constant value: that note is outside the instrument's range, or the key
  is unpitched (a tap or noise key). Stay inside the range.
- A real offset error: pin `offset = N` in the catalog entry (an alias or an
  `[[override]]` in `musicengine/catalog_data/overrides.toml`) and re-check.

## Reproducibility after engine changes

Seeds are fixed, so the same script and engine produce identical WAVs. After changing the
engine, run `python -m pytest` in the repo: `tests/test_golden.py` renders a short piece
with real samples and compares its PCM hash (local only; it needs the sample library). A
difference means the change altered the sound; regenerate with
`MUSICENGINE_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py` only when intended.

## Reporting

- Say what was measured: pitches, seam, clipping, level arc, licenses. Say plainly that you
  did not listen.
- Point out where something might sound wrong despite good numbers: a synthesized
  instrument carrying a lead, an instrument used for the first time, a note at the edge of a
  range.
- Hand over the WAV path (and stems, MIDI, OGG if rendered), plus `python -m musicengine
  credits <render>.render.json` for the sources used.
