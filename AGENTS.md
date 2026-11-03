# AGENTS.md: making music with music-engine

This file teaches an AI coding agent (Claude Code, Codex, Cursor, Aider and the like) how to
turn a music request into a finished, verified render with this repo. Read it fully before
writing any notes. The detailed references live in `docs/agents/`:

| File | Load when |
|---|---|
| [docs/agents/brief.md](docs/agents/brief.md) | understanding a request: use → form, mood → harmony, genre conventions, prompts and reference tracks, questions worth asking |
| [docs/agents/composition.md](docs/agents/composition.md) | planning and writing: form, harmony, melody and motif, voicing, ranges, orchestration, arrangement, game music |
| [docs/agents/engine.md](docs/agents/engine.md) | producing: Score / stem / line / fx / kit API, instrument names, synth rules, MIDI, stems |
| [docs/agents/verify.md](docs/agents/verify.md) | after every render: the gates, what the numbers mean, per-stem diagnosis, reporting |
| [docs/agents/variants.md](docs/agents/variants.md) | optional: fanning a new track out into several variants with sub-agents |

## The one fact that shapes everything

**You cannot listen.** Every judgement about a render comes from measurement: `verify`,
`analyze`, `loudness`, `hiss`, `check`. Never claim a track "sounds" anything. Report what you
measured and say that you did not listen.

## Setup

```
pip install -e ".[dev]"          # from the repo root; Python 3.11+
ffmpeg -version                  # must be on PATH (every render writes an .ogg)
python -m musicengine search cello
```

Samples download on first use into `~/SoundLibrary` (override with `MUSICENGINE_LIBRARY`).
This needs `git`, internet access and several GB of disk. `python -m musicengine fetch
<names>` downloads ahead of time; do it before a long render.

## Workflow

Three phases, in order: **understand → plan → produce (compose, render, verify, revise)**.
Most bad results come from skipping the first two and writing notes from a vague brief.

### 1. Understand the request

Turn the request into concrete parameters before writing anything ([brief.md](docs/agents/brief.md)).
A request can be a sentence, a free-text prompt, a reference ("like Interstellar"), a scene
description, or a MIDI file.

- **Use**: what plays it, where, and how long. It decides the form: menu or exploration
  background → seamless loop; cutscene or trailer → one-shot cue with an arc; stinger →
  2–8 s; song → intro, verse, chorus…; adaptive game music → stems.
- **Genre, mood, energy curve.** Map adjectives to musical decisions: "hopeful" →
  major/Lydian, rising contours; "tense" → pedal tones, minor 2nds, ostinati.
- **References.** Name what defines each reference: instruments, tempo, harmony, texture,
  production. Borrow the technique, never the melody. For a local reference *file* the user
  gives (never download one): `python -m musicengine reference <file> <dir>/reference.json`,
  then put that path in plan.json `reference`.
- **Hard constraints**: length, tempo, key, loopability, deliverables (WAV/OGG, stems, MIDI).
- **Catalog check.** Look up every instrument the brief implies with
  `python -m musicengine search …`. If an acoustic sound has no recording in the catalog,
  propose a recorded substitute; do not quietly fall back to a `synth/…` patch.
- If something is impossible (for example sung lyrics: `choir` and `voice` sing one vowel),
  say so up front.

Ask only what changes the plan, batched, each with a recommended default. Skip asking for
small or fully specified requests.

### 2. Write plan.json

Write the plan before any code, e.g. as `music/<track>/plan.json` in the user's project. The
format is the docstring of `musicengine/plan.py`; `examples/plans/war_theme.plan.json` is a
complete example.

```
python -m musicengine plan check music/<track>/plan.json      # must print OK
python -m musicengine plan summary music/<track>/plan.json    # show this to people, not the JSON
```

The plan holds:
- **global**: bpm, beats_per_bar, key, mode, bars, loop, and optionally the mastering
  `genre` and `target_lufs`.
- **sections**: per section its bars `[start, end)`, function (intro/A/B/build/peak/
  breakdown/outro), chords (one per bar, or a cycle), dynamic (pp…ff), and the instruments
  with their role (melody, countermelody, harmony, bass, rhythm, color) and stem.
- **motif**: 2–12 `[midi, beats]` pairs (3–7 notes is the sweet spot), plus how it is
  varied.
- **mix** (optional): per-stem `level_db`, `reverb`, `role`.
- **rationale**: every major decision with its `why`, and optionally a `source` pointing at
  the doc section it came from (e.g. `docs/agents/composition.md#rhythm-and-groove`).
- **synth** (optional): a sentence saying why synthesized sound belongs in this piece. Only
  for the synth cases below. Its presence turns `allow_synth` on through `plan.score`.
- **reference** (optional): a reference.json; the master leans toward its balance and verify
  compares against it.
- **verify** (optional): `chroma_min`, `dynamics_min_rho` thresholds.

The chords and dynamics are not decoration: verify measures the render against them.

For a substantial piece, show the summary and get a yes before composing.

### 3. Compose with Score

One Python script per track (e.g. `music/<track>/track.py`), run with `python -I`. Build the
Score from the plan and follow it section by section ([engine.md](docs/agents/engine.md)).

```python
from musicengine import plan
from musicengine.score import Score, chord_run, voice, bass

p = plan.load("music/my_track/plan.json")
s = plan.score(p, seed=1)                       # fixed seed: the render is reproducible
CHORDS = plan.chords(p)                         # pitch classes per bar

s.stem("strings", level_db=-22, reverb=0.45, width=1.2)
s.stem("bass", level_db=-21, reverb=0.2, role="bass")
s.stem("lead", level_db=-20, reverb=0.35)
s.stem("drums", level_db=-20, reverb=0.15, role="drums")

for bar, pcs in enumerate(CHORDS):
    run = chord_run(CHORDS, bar)                # bars this chord lasts; 0 = still the previous one
    if run:
        beats = run * s.bpb
        s.notes("strings", "violins", bar, 0, beats, voice(pcs, 62, 76)[:3], vel=0.5)
        s.note("bass", "celli", bar, 0, beats, bass(pcs, 36), vel=0.55)
    for q in range(s.bpb):
        s.note("drums", "drumkit", bar, q, 0.5, 36 if q % 2 == 0 else 38, 0.7)

# melodies are played, not placed: legato, swells on long notes, phrase shaping
s.line("lead", "horns", [(8, 0, 1.5, 69, 0.6), (8, 1.5, 0.5, 70, 0.6), (8, 2, 2, 72, 0.65)])

s.render("music/my_track/out/my_track", stems=False, midi=True)
```

That is a skeleton, not a track: it ignores the plan's per-section instruments and dynamics,
so verify will (correctly) warn about the dynamics arc and may fail the loop seam. A real
script follows every section of the plan.

Rules that matter:
- Every melodic or countermelodic line goes through `s.line(...)`. `s.note` / `s.notes` are
  for chords, pads, bass notes, ostinati and drums. Mark detached passages (staccato,
  pizzicato, spiccato, repeated notes) with `legato=False`.
- Place sustains with `chord_run`, so a held note never spills into the next chord.
- Stay inside instrument ranges ([composition.md](docs/agents/composition.md)).
- Declare stems with `role=` (drums, bass, percussion, guitar, keys, vocal…) to get the
  genre preset's stem processing.
- Loops: the last bar leads back into bar 1; tails and LFOs wrap across the seam
  automatically.

### 4. Render

`Score.render(out_base, stems=…, midi=…)` writes `<out_base>.wav` (48 kHz/24-bit), `.ogg`,
`.render.json` (instruments, library commits, licenses, credits, master settings, loudness),
and optionally `_stems/*.wav` (they sum to the mix) and `.mid`. The master always runs: genre
EQ, glue compressor, true-peak limiter to −16 LUFS / −1 dBTP by default.

`render()` raises if the score uses synthesized sources without `allow_synth`. Do not "fix"
that by forcing `allow_synth=True`; replace the source with a recording, or add a genuine
`"synth"` reason to the plan.

### 5. Verify by measurement

```
python -m musicengine verify music/my_track/plan.json music/my_track/out/my_track.wav
python -m musicengine hiss music/my_track/out/my_track.wav
```

verify exits 1 on any FAIL and writes `<render>.verify.json`. The gates
([verify.md](docs/agents/verify.md)):

| Gate | Fails the render when |
|---|---|
| licenses | a source is not CC0/Unlicense, or `Synthesized` appears without a plan `"synth"` reason |
| clipping | any clipped sample |
| length | a loop is not exactly the planned bars, or a one-shot is shorter |
| loop seam | the step at the seam is larger than the steps around it |
| loudness | integrated LUFS is more than 1 LU off the target |
| true peak | the wav exceeds the ceiling |

WARN (look at each, mention it in the report): ogg true peak, limiter above ~3 dB, chroma
agreement below `chroma_min`, a dynamics arc that does not follow the plan, a loop whose
first and last section differ by more than 6 dB. Chroma counts overtones; a weak bar is a
lead to investigate per stem, not proof of a wrong note.

Nothing is shown to anyone while verify FAILs.

### 6. Revise

- Treat feedback as plan changes first, then code changes. Update plan.json, re-run
  `plan check`, edit the script, re-render, re-verify.
- Change one thing at a time when chasing a measurement (a stem level, an instrument, a
  voicing), so the next verify tells you what moved.
- Multi-track work (an OST, an album): finish one track, get the reaction, then do the rest
  with the same palette and motif.

### 7. Report

- Hand over the WAV path (and OGG, stems, MIDI if rendered).
- Say what you measured (verify status, LUFS, true peak, chroma, seam) and that you did not
  listen.
- Point out where something may sound wrong despite good numbers.
- List the decisions you made for the user (tempo, key, instruments, substitutions).
- `python -m musicengine credits <render>.render.json` lists the sources used.

## Recordings by default, synths where they belong

`Score` refuses software-synthesized sources unless `allow_synth=True`, which a plan turns on
with a `"synth"` reason. Use synths only when:
- the genre is synth-native: synthwave/retrowave, house/techno/trance/EDM, dubstep, DnB,
  chiptune/8-bit, trap and 808 hip-hop, 80s/electro-pop, cyberpunk or sci-fi electronic,
  electronic ambient;
- the user asks for a synth sound or names a synth instrument; or
- a hybrid piece uses a synth as a deliberate colour layered on recordings (a trailer pulse,
  a sci-fi drone), named in the plan as such.

Otherwise everything comes from recordings: an orchestral, folk, jazz, rock, acoustic lo-fi
or world piece gets recorded drums, bass and pads, never a synth stand-in. Recordings of real
hardware synths and drum machines are recordings. Processing recordings (EQ, compression,
reverb, distortion, sidechain, filter sweeps, pitch and time edits) is always fine.

## Licenses and copying

- Every catalog library is a public-domain dedication (CC0, Unlicense). The fetcher refuses
  libraries whose declared license is anything else and scans downloaded license/readme files
  for attribution, ShareAlike and NonCommercial wording. This is a heuristic, not legal
  advice: the `.render.json` lists every source so a user can check before releasing.
- A render's `.render.json` `licenses` must list only `CC0-1.0` or `Unlicense`, plus
  `Synthesized` only when the plan has a `"synth"` reason.
- Never add a CC-BY, MIT, Sampling Plus, ShareAlike or NonCommercial source. New libraries go
  into `musicengine/catalog_data/libraries.toml` only after reading their license files.
- No melodies, lyrics or recordings lifted from existing music. Styles and techniques are
  fine.

## CLI

```
python -m musicengine search cello                    # find instruments (name/path/family words)
python -m musicengine search --family drums snare
python -m musicengine info <name>                     # catalog entry, license, credit
python -m musicengine fetch <names...>                # download + calibrate now
python -m musicengine check <name>                    # render notes across the range, measure pitch
python -m musicengine plan check|summary plan.json
python -m musicengine verify plan.json track.wav      # every gate against the plan; exit 1 on FAIL
python -m musicengine analyze track.wav <bpm> <beats_per_bar> [chords.json]
python -m musicengine loudness track.wav              # LUFS, LRA, true peak, PLR
python -m musicengine hiss track.wav                  # >6 kHz energy, click-like spikes
python -m musicengine reference song.wav [out.json]   # measure a local reference track
python -m musicengine compare track.wav song.reference.json
python -m musicengine credits track.render.json       # sources a render used
```

After `pip install`, `musicengine <command>` works the same as `python -m musicengine`.

## Working on the engine itself

- `python -m ruff check .` and `python -m pytest -m "not samples"` must pass (CI runs them).
- `python -m pytest` also runs the `samples` tests, including a golden-hash render that
  catches unintended sound changes; they need the sample library and are local only.
  Regenerate the hash only for an intended change.
- Keep stems summing to the mix, loops seamless and renders reproducible for a fixed seed.
