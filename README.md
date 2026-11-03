# music-engine

A music engine built to be driven by AI coding agents: an agent writes a plan, composes the
piece in Python from public-domain recordings of real instruments, renders it, and checks the
result by measurement, because it cannot listen.

Point Claude Code, Codex or another coding agent at this repo and ask for music ("a 2-minute
seamless loop for a calm exploration level, harp and flute"). [AGENTS.md](AGENTS.md) teaches
the agent the whole workflow:

1. **Understand** the request: use, form, length, mood, genre, references, hard constraints.
2. **Plan** the piece in `plan.json`: sections, chords per bar, dynamics, motif, instruments,
   mix, and the reason for every decision.
3. **Compose** with the `Score` API: notes, chords, played melody lines, drums, effects.
4. **Render** to WAV/OGG (plus stems and MIDI), mastered to a loudness target.
5. **Verify** by measurement: licenses, clipping, length, loop seam, loudness, true peak,
   chroma against the planned chords, the dynamics arc.
6. **Revise** until verify passes, then report what was measured.

It is also an ordinary Python library and CLI, so a person can use it the same way.

## Features

- **About 2,700 catalog instruments**, each pinned to a commit of a public-domain (CC0 /
  Unlicense) sample library: VSCO 2 CE, VCSL, FreePats, sfzinstruments / Karoryfer, Sonic Pi.
  They download on first use.
- **Recordings by default.** `Score` refuses software-synthesized sources unless a score opts
  in with `allow_synth=True` (a plan opts in with a written `"synth"` reason). The built-in
  synths (subtractive, FM, chip, Karplus-Strong, formant, 808/909 machines) are there for
  synth-native styles.
- **Playing, not just placing**: `Score.line` joins legato notes, swells long notes by
  crossfading the soft and loud recordings, and shapes phrases.
- **Effects**: EQ and filter automation, compressor, sidechain ducking, gate, distortion,
  guitar/bass amp + cabinet, chorus, flanger, phaser, tremolo, Leslie, ping-pong and tape
  delay, tape, bitcrush, stereo width, and a convolution hall.
- **Seamless loops**: tails wrap across the seam, LFOs are rounded to whole cycles per loop,
  automation repeats every cycle. One-shot cues keep their reverb tail.
- **Master**: low end to mono, genre EQ, glue compressor and a true-peak limiter to
  −16 LUFS / −1 dBTP by default, with genre presets and an optional tonal match to a
  reference track.
- **Stems that sum to the mix** (for adaptive game music) and **MIDI out**; **MIDI in** plays
  any MIDI file with the catalog instruments.
- **Measurement tools**: `verify` (everything against plan.json), `analyze`, `loudness`
  (BS.1770 / EBU R128), `hiss`, `check` (pitch across an instrument's range), `reference` /
  `compare` against a local reference track.
- **Provenance**: every render writes a `.render.json` with the instruments, library commits,
  licenses and credits it used.

## Coverage

| Area | Sources |
|---|---|
| Orchestra | VSCO 2 CE, VCSL: strings in all articulations, winds, brass, harp, timpani, organs |
| Keys | VCSL Steinway B / Kawai grands, uprights, harpsichords; FreePats upright & old piano; synth e-pianos, clav and drawbar organs |
| Guitars & basses | FreePats nylon, clean, jazz, direct (for amp sim), distortion; Karoryfer acoustic & electric; electric/upright basses; ukulele, banjo |
| Mallets & bells | vibraphone (incl. bowed), marimba, xylophone, glockenspiel, tubular bells, kalimba, hang, steel drum |
| World | sampled erhu, bagpipe, accordion, harmonica, zithers, ocarina, tabla, darbuka, cajon, bongos, congas, shakers; synthesized sitar, koto, guzheng, shamisen, oud, mandolin, balalaika, hammered dulcimer, duduk, shakuhachi, bansuri, pan flute |
| Drums | Karoryfer Big Rusty / Unruly / Swirly / Virtuosity kits (real acoustic, CC0); Sonic Pi hits; synthesized 808 & 909 machines |
| Voices | `choir`: one recorded male singer (Karoryfer) stacked into a section, MIDI 36–63, "a" vowel only; Karoryfer vocal sustains; formant-synth choir and solo vowels (synthesized, need `allow_synth`) |
| Synths | subtractive (leads, basses, pads, plucks, brass, strings), chip (pulse/square/triangle), FM, FreePats synth sets |

No CC0 recording was found for sitar, koto, shamisen, oud, mandolin, celesta, Rhodes or a
TR-909, so those are synthesized and tagged as such.

## Requirements

- Python 3.11 or newer (numpy, scipy, soundfile and matplotlib are installed with the package).
- `ffmpeg` on PATH: every render also writes an `.ogg`.
- `git` on PATH: sample libraries are fetched from their GitHub repositories.
- Internet access on first use of each library, and several GB of free disk in
  `~/SoundLibrary` (or wherever `MUSICENGINE_LIBRARY` points).
- `sfizz_render` for SFZ programs that need loop points, filters or CC crossfades (the acoustic
  `drumkit` is one). On Windows it is downloaded automatically (see Privacy and security). On
  Linux and macOS install sfizz yourself so `sfizz_render` is on PATH, or set
  `MUSICENGINE_SFIZZ_RENDER`; without it those programs fall back to the built-in SFZ reader
  with a warning, or fail with install hints when the reader cannot play them.
- For the agent workflow: any AI coding agent that can run shell commands and edit files.

## Install

From GitHub Releases: download the wheel from the [latest release](../../releases/latest)
and install it:

```
pip install musicengine-0.2.0-py3-none-any.whl
```

Or from a clone (recommended when an agent will work in the repo, since AGENTS.md and the
docs live here):

```
git clone <this repository's URL> music-engine
cd music-engine
pip install -e .
```

Both give you `python -m musicengine ...` and a `musicengine` command.

## Usage

### With an AI coding agent

Open the repo (or a project that has music-engine installed and a copy of AGENTS.md and
`docs/agents/`) in your agent and describe what you want: use, length, mood, instruments,
references, deliverables. The agent follows [AGENTS.md](AGENTS.md): it writes
`music/<track>/plan.json`, shows you a summary, composes `music/<track>/track.py`, renders,
runs `verify`, and hands you the WAV with the measurements. Give feedback in musical terms
("the horns are too loud in the peak", "make the B section sparser") and it revises the plan
and re-renders.

### By hand

```python
from musicengine.score import Score, bass, voice

s = Score(bpm=96, bars=8, seed=1, genre="cinematic")    # loop=False for a one-shot cue
s.stem("strings", level_db=-21, reverb=0.4)
s.stem("low", level_db=-22, reverb=0.3, role="bass")
s.stem("drums", level_db=-20, reverb=0.15, role="drums")
chords = [[9, 0, 4], [5, 9, 0], [0, 4, 7], [7, 11, 2]] * 2   # Am F C G as pitch classes
for b, pcs in enumerate(chords):
    s.notes("strings", "violins", b, 0, 4, voice(pcs, 60, 76)[:3], vel=0.55)
    s.note("low", "celli", b, 0, 4, bass(pcs, 36), vel=0.6)
    for q in range(4):
        s.note("drums", "drumkit", b, q, 0.5, 36 if q % 2 == 0 else 38, 0.7)
s.render("out/track", stems=True, midi=True)   # .wav .ogg .mid _stems/ .render.json
```

Synth-native styles opt in to synthesized sound explicitly:

```python
from musicengine import catalog
from musicengine.score import Score

s = Score(bpm=124, bars=4, seed=1, allow_synth=True)   # house: synths belong here
s.stem("kick", level_db=-17, reverb=0.0)
s.stem("bass", level_db=-21, fx=[("duck", {"key": "kick", "depth_db": -6})])
kick = catalog.kit("synth/drum-machine-909", "*_kick_rr*")
for b in range(4):
    for q in range(4):
        s.hit("kick", kick[0], b, q)
    s.note("bass", "synth/acid-bass", b, 0.5, 0.4, 33, 0.8)
s.render("out/house")
```

Check a render:

```
python -m musicengine loudness out/track.wav
python -m musicengine analyze out/track.wav 96 4
python -m musicengine credits out/track.render.json
```

With a plan: `python -m musicengine plan check plan.json`, then
`python -m musicengine verify plan.json out/track.wav`. `examples/plans/war_theme.plan.json` is
a complete plan; `examples/genre_demos.py` renders house, rock, jazz, lo-fi, east-asian,
indian, middle-eastern, chiptune and choir demos; `examples/performance_demo.py` renders one
melody placed and performed.

To audition renders in a browser: `python -m http.server 8000 --bind 127.0.0.1 --directory out`.

### CLI

```
python -m musicengine search cello                    # find instruments
python -m musicengine search --family drums snare
python -m musicengine info drumkit                    # catalog entry, license, credit
python -m musicengine fetch horns violins             # download + calibrate ahead of time
python -m musicengine check celli                     # measured pitch across the range
python -m musicengine plan check|summary plan.json
python -m musicengine verify plan.json out/track.wav  # every check against the plan
python -m musicengine analyze out/track.wav 124 4 [chords.json]
python -m musicengine loudness out/track.wav          # LUFS, LRA, true peak, PLR
python -m musicengine hiss out/track.wav
python -m musicengine reference song.wav              # -> song.reference.json
python -m musicengine compare out/track.wav song.reference.json
python -m musicengine credits out/track.render.json   # sources a render used
```

Short names for common instruments are in `musicengine/catalog_data/aliases.toml`: `violins`,
`celli`, `horns`, `piano`, `organ_loud`, `vibes`, `harp`, `drumkit`, `world_perc`, `choir`
and so on. Project-specific instruments go through `catalog.register(...)`.

## Licensing of samples and output

The policy: everything a render can contain is either a public-domain recording (CC0 /
Unlicense) or synthesized by this code, so the music you make belongs to you, with no
attribution or royalties owed.

- Excluded on purpose: CC-BY (Salamander, DrumGizmo…), MIT (MuseScore_General/FluidR3),
  Sampling Plus (Sonatina), ShareAlike, NonCommercial.
- Each library's declared license is checked against that list, and the fetcher scans every
  downloaded library's license/readme files for attribution, notice, ShareAlike and
  NonCommercial wording and refuses the library if it finds any.
- This check is a heuristic, not legal advice. Upstream licenses can be mislabelled. Every
  render's `.render.json` lists the instruments, library commits and licenses it used
  (`python -m musicengine credits` prints the credits); check those before a commercial
  release.
- The external renderers (sfizz: BSD-2-Clause; FluidSynth: LGPL-2.1) are separate programs.
  Their licenses cover the programs, not the audio they render.

## Limitations and known issues

- No sung lyrics: `choir` and `voice` sing a vowel only. The recorded choir covers MIDI 36–63;
  notes outside that are pitch-shifted and sound it.
- The built-in SFZ reader ignores filters, LFOs and CC crossfades. Programs that rely on loop
  points, offsets or crossfades need `sfizz_render`.
- The pitch detector behind `check` can be off by an octave on mixture organ stops, bells and
  drums. Pinned offsets in the catalog cover the known cases (see `organ_loud`). Timpani pitch
  is unverified.
- The synthesized world instruments and the formant choir are convincing in a mix but are not
  recordings. Prefer a sampled instrument whenever one exists.
- The sample-based golden test compares a PCM hash that depends on numpy/scipy versions, so
  it runs locally only.
- `verify` measures; it cannot tell whether music is good. A render can pass every gate and
  still need human ears.
- There is no GUI.

## Troubleshooting

- **`this score uses synthesized sound, and recordings only is the default`**: replace the
  listed sources with recordings, or, for a synth-native piece, create the score with
  `allow_synth=True` (or add a `"synth"` reason to the plan).
- **`ffmpeg` not found / `FileNotFoundError` at the end of a render**: install ffmpeg and put
  it on PATH.
- **`sfizz_render was not found on PATH`** (Linux/macOS): install sfizz, or set
  `MUSICENGINE_SFIZZ_RENDER=/path/to/sfizz_render`.
- **A fetch is refused with `LicenseProblem`**: the library's license files mention a
  forbidden license; choose another instrument.
- **A fetch was interrupted**: run `python -m musicengine fetch <name>` again; it only fetches
  what is missing.
- **verify FAILs on loudness or true peak**: lower or compress the loudest stem (usually
  drums); render.json `master.limiter_max_gr_db` shows how hard the limiter worked.
- **Chroma agreement is low**: overtones and low sustains lower it; check each stem in the
  weak bars (see `docs/agents/verify.md`) before changing notes.

## Privacy and security

- Everything runs locally. Nothing is uploaded, and there is no telemetry.
- Network access: sample libraries are cloned from their public GitHub repositories at a
  pinned commit. On Windows, when `sfizz_render` / `fluidsynth` is not on PATH, the pinned
  official release zip of sfizz 1.2.3 or FluidSynth 2.6.1 is downloaded from its GitHub
  releases page, checked against a SHA-256 stored in `musicengine/external.py`, and only then
  extracted and run. Set `MUSICENGINE_SFIZZ_RENDER` / `MUSICENGINE_FLUIDSYNTH` to use a copy
  you installed yourself.
- Stored on disk: samples, downloaded tools, per-note render caches and measured sample
  levels in `~/SoundLibrary` (or `MUSICENGINE_LIBRARY`); renders wherever you write them.
- `reference` reads only local audio files you pass to it; it does not extract melodies.

## Development

```
pip install -e ".[dev]"
git config core.hooksPath .githooks     # lint + fast tests before every commit
python -m ruff check .
python -m pytest -m "not samples"        # what CI runs
python -m pytest                         # all, including sample renders (needs the sample library)
python -m build                          # sdist + wheel into dist/
```

Rebuilding the catalog: `python -I scripts/build_catalog.py --sfzorg --freepats` regenerates
`musicengine/catalog_data/generated/` and re-pins the sfzinstruments and FreePats repositories
at their current HEAD (needs the `gh` CLI, logged in). Other libraries are added to
`musicengine/catalog_data/libraries.toml`, but only after you have read their license files
yourself.

Releases: pushing a tag `v*` (e.g. `v0.2.0`) runs `.github/workflows/release.yml`, which runs
the tests, builds the sdist and wheel, and attaches them to a GitHub Release. It needs no
secrets beyond the default `GITHUB_TOKEN`; nothing is published to PyPI.

## Disclaimer

This project is not affiliated with or endorsed by any company, product or sample library
mentioned here (including Anthropic, OpenAI, Versilian Studios, FreePats, Karoryfer Samples,
Sonic Pi, sfizz, FluidSynth, Steinway, Kawai, Yamaha or Roland). Names are used only to
describe compatibility or sources. The license checks are best-effort; you are responsible
for verifying that your use of the samples and of the output fits your needs. Use at your own
risk.

## License and credits

The code is released under the [MIT License](LICENSE), copyright (c) 2026 iefedev.

Sample libraries (downloaded on demand, not included in this repository) are public-domain
dedications by their authors: VSCO 2 Community Edition and the Versilian Community Sample
Library (Versilian Studios), FreePats, the sfzinstruments organisation and Karoryfer Samples,
and the Sonic Pi sample set. A render's `.render.json` lists the exact libraries and commits
it used. Optional external renderers: sfizz (BSD-2-Clause) and FluidSynth (LGPL-2.1). Python
dependencies: numpy, scipy, soundfile (libsndfile), matplotlib.
