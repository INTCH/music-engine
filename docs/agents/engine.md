# music-engine API (for producing)

Worked examples in this repo:
- `examples/genre_demos.py`: house, rock, jazz, lo-fi, east-asian, indian, middle-eastern,
  chiptune, choir
- `examples/performance_demo.py`: the same melody placed note by note and played as a line
- `examples/plans/war_theme.plan.json`: a complete plan

Run track scripts with `python -I script.py` (isolated mode: the script's folder is not put on
`sys.path`, so a stray file there cannot shadow a module).

## Skeleton

```python
from musicengine import catalog, plan
from musicengine.score import Score, chord_run, voice, bass

p = plan.load("music/my_track/plan.json")
s = plan.score(p, seed=1)            # bpm, bars, meter, loop, genre, reference, allow_synth from the plan
# s = Score(bpm=96, bars=32, beats_per_bar=4, seed=1, genre="cinematic")   # without a plan
# s = Score(..., loop=False, tail=10.0)                        # one-shot cue with reverb tail
CHORDS = plan.chords(p)              # pitch classes per bar

s.stem("strings", level_db=-21, reverb=0.45, width=1.2)
s.stem("drums", level_db=-19, reverb=0.15, role="drums")      # role: the genre preset's stem fx
s.stem("bass", level_db=-21, reverb=0.1, role="bass", fx=[("duck", {"key": "drums", "depth_db": -6})])

s.note("strings", "violins", bar, beat, beats, midi, vel=0.6)     # bar 0-based, beat float
s.notes("strings", "violas", bar, beat, beats, [55, 62], vel=0.5)
s.line("lead", "solo_violin", [(bar, beat, beats, midi, vel), ...])  # a played melody
s.hit("drums", path, bar, beat, gain=1.0)                          # one-shot sample file
s.audio("fx", numpy_stereo_array, bar, beat)                       # any rendered audio (48 kHz)

out, levels, limiter = s.render("music/my_track/out/my_track", ir_seconds=4.5, stems=False, midi=False)
```

- `Score.note(..., human=0.006, attack=None, release=None, cents=0, swell=None)`: the extra
  keywords override the instrument's envelope for that note. Use `human=0` for tight grids.
  `swell` shapes a long note's dynamic (below).
- `Score.line(stem, inst, notes, legato=True, phrase=True, swell_long="hairpin",
  long_beats=2.0, xf=0.07, rit=0.08)` (`musicengine/perform.py`): a melodic line played
  like a player. `notes` = `[(bar, beat, beats, midi, vel), …]`, optionally with a 6th item
  of per-note options, e.g. `{"swell": "cresc"}` or `{"swell": None}`. One voice per call;
  not for chords.
  - legato: notes that touch (within 50 ms) are joined. The next note enters past its
    attack, with an equal-power crossfade, at the previous note's level, easing to its own
    over 0.5 s. A rest re-articulates; a repeated pitch keeps half its attack.
  - swell: notes of `long_beats` or more get `swell_long` unless they set their own. Named
    curves: hairpin (< >, default), cresc, dim, fp, bloom, flat, or `[(pos, level), …]`
    breakpoints. The soft and the loud recording of the note are crossfaded along the curve,
    so the timbre follows the dynamic.
  - phrase: phrases split at rests of a beat or more; velocities arch toward the highest note,
    the last note is softer, and the last onsets drift up to `rit` beats late. Short rhythmic
    or detached phrases over a pizzicato or drum grid drag with that on every bar: pass
    `rit=0.02` or so, and `legato=False` for staccato, pizzicato or repeated-note figures.
- `chord_run(cycle, bar)` → how many bars the chord starting at this bar lasts, or 0 if
  `bar` continues the previous chord. Sustains should last exactly that long, or a held note
  spills over the next chord.
- `voice(pitch_classes, lo, hi)` → every chord tone between MIDI lo and hi.
  `bass(pitch_classes, lo=36)` → the root at or above `lo`.
- `s.t(bar, beat)` → seconds, and `s.beat` → seconds per beat (use these for delay times
  and automation points). Automation (`sweep` points, `duck` times) is score time: pass
  `s.t(...)` as is and never add `s.pre`; the stem adds the pre-roll, and in a loop the
  points repeat every cycle (the curve runs from the last point round to the first).
- `render` writes:
  - `.wav` (48 kHz/24-bit) and `.ogg` (needs `ffmpeg` on PATH)
  - `.render.json`: instruments, library commits, licenses, credits, master settings,
    loudness (LUFS, LRA, true peak of the wav and the ogg), `recorded_only`, `synthetic`
  - `_stems/*.wav` with `stems=True`. The stems sum exactly to the mix.
  - `.mid` with `midi=True`

## Master

`Score(genre=None, target_lufs=-16.0, ceiling_dbtp=-1.0, reference=None)`
(`musicengine/mastering.py`):
- Chain: 28 Hz low cut → low end to mono (below 80–150 Hz by genre) → genre EQ → optional
  reference-match EQ (±4 dB max, from `reference.json`) → glue compressor → true-peak
  limiter → gain to the LUFS target.
- Genre presets (`mastering.PRESETS`): default, orchestral, ambient, cinematic, rock, pop,
  electronic, lofi, jazz, folk, chiptune, world; aliases (`mastering.ALIASES`) such as house,
  techno, synthwave, trailer, metal, hiphop, celtic, horror. A preset also gives
  `stem(..., role=...)` an fx chain: drums get parallel compression, bass gets glue and
  warmth, lo-fi keys get tape.
- `stems=True` renders skip the glue compressor, so a layer heard alone does not pump on
  hits it does not contain. Stingers (under 10 s) aim 2 LU lower.
- render.json `master.limiter_max_gr_db` above about 3 dB means one stem (usually drums) is
  hitting the limiter; lower or compress it.

## Stems

`s.stem(name, level_db=-20, pan=0, width=1, reverb=0.3, hp=None, lp=None, delay=None,
autopan=None, fx=None, role=None)`
- `level_db`: loudness of the stem while it plays. Libraries differ in level, so set it by
  role (table in [composition.md](composition.md)). Dynamics within the stem come from note
  velocities.
- `delay=(seconds, feedback, wet, lowpass_hz)`: ping-pong delay.
- `autopan=(rate_hz, depth)`: slow left-right drift.
- In loop renders every LFO (autopan, chorus, flanger, phaser, tremolo, leslie, tape wow and
  flutter) is rounded to a whole number of cycles per loop, so the seam stays smooth; do not
  round rates by hand. One-shots keep the exact rates.
- `fx=[(name, params), ...]`: an effect chain. It runs at −18 dBFS, before leveling.

## Effects (`musicengine.fx`)

| fx | params (defaults) | use |
|---|---|---|
| eq | list of (kind, freq, gain_db, q); kind: lp hp bp notch peak lowshelf highshelf | `("eq", [("hp", 120), ("peak", 3000, -3, 1)])` |
| sweep | kind="lp", start, end, q, or points=[(s.t(bar), hz), ...] | filter risers and automation |
| compressor | threshold_db=-18, ratio=4, attack=.01, release=.15, makeup_db, key | glue, taming drum peaks |
| duck | key="stem" or times=[s.t(...), ...], depth_db=-8, attack, release=.25 | sidechain pumping |
| gate | threshold_db=-50 | trimming tails |
| distortion | drive=6, kind=tanh/tube/hard/fuzz/fold, tone=6000, mix | saturation, grit |
| amp | voicing=clean/crunch/lead/metal/bass, gain=1, cabinet=True | guitar and bass amp + cab |
| chorus | rate=.8, depth_ms=3, delay_ms=12, voices=2, mix=.5 | width, 80s |
| flanger | rate=.25, depth_ms=2, feedback=.5, mix=.5 | jet sweep |
| phaser | rate=.3, stages=6, low=300, high=3000, mix=.5 | movement |
| tremolo | rate=5, depth=.5, shape=sine/square | amplitude wobble |
| leslie | speed=slow/fast | organ rotary speaker |
| delay | seconds=.375, feedback=.4, mix=.3, lp=4000, pingpong=True | echoes |
| tape | saturation=1.5, wow, flutter, tone=12000 | lo-fi warmth (no hiss) |
| bitcrush | bits=8, downsample=1 | chip and lo-fi grit |
| width | amount | stereo width |

## Finding instruments

```
python -m musicengine search <words>               # e.g. "tenor sax", "harpsichord", "conga"
python -m musicengine search --family <family> <words>
python -m musicengine info <name>                  # entry, license, credit
python -m musicengine check <name>                 # measured pitch across the range
python -m musicengine fetch <names...>             # download + calibrate ahead of time
```

Families: strings, guitar, bass, keys, woodwinds, brass, mallets, harp, drums, voice, fx,
synth, other. Sources:
- `vsco/…`, `vcsl/…`: orchestral and world samples
- `freepats-…/…`: pianos, guitars, basses, accordion, ukulele, timpani, world percussion
- `karoryfer-…/…`: acoustic kits, real handclaps (`karoryfer-frankensnare/claps-*`),
  electric basses (`black-and-blue-basses`, `big-little-bass`), guitars, sax, tuba, cello
- `body-percussion/…`: claps, snaps, stomps
- `sonicpi/acoustic-kit`, `sonicpi/tabla`

**Recordings by default.** `Score(...)` refuses synthesized sources by default and names them.
That covers `synth/…`, the built-in drum machines, and every library in
`musicengine/catalog_data/synthetic.toml` (for example the FreePats sets rendered from
software synths, and Sonic Pi kits of unknown origin). Recordings of hardware count as
recordings: the VCSL TX81Z (sampled from the FM hardware) and caveman-cosmonaut (a transistor
organ). So do acoustic recordings used in synth-style programs (cowsynth, squynth,
string-cyborgs). `render.json` records `recorded_only`.

A piece in one of the synth cases (see [AGENTS.md](../../AGENTS.md)) puts its reason in
plan.json `"synth"`; `plan.score(p)` then passes `allow_synth=True`, and verify accepts the
synthesized sources. Do not set `allow_synth=True` by hand just to get past the refusal.
Audio passed to `s.audio()` is not checked, so never feed it synthesized output in a
recordings-only piece. When the piece is not a synth case, use these recorded replacements:

| instead of | use |
|---|---|
| 808/909 kick, snare, hats | Karoryfer acoustic kits (`drumkit`, `karoryfer-big-rusty-drums/…`, `swirly`, `unruly`), processed with compressor/EQ/gate for electronic punch |
| synth clap | `karoryfer-frankensnare/claps-stack`, `body-percussion/body-handclap` |
| synth/sub/acid bass | electric bass (`karoryfer-black-and-blue-basses/…`, `freepats-electric-bass-yr/…`) + amp/distortion fx |
| saw/square lead | `freepats-electric-guitar-fsbs-*` through the `amp` fx, violins, trumpet |
| pads | strings (susvib), `organ_*`, `vibes_bowed`, VCSL wine glasses |
| celesta / music box / fm-bell | `glock`, `vibes`, VCSL tubular glockenspiel, hand chimes |
| choir | `choir` (one recorded male singer stacked into a section; MIDI 36–63, "a" vowel only) |

**Aliases** (short names with tuned envelopes, in `musicengine/catalog_data/aliases.toml`):
- strings: violins, violas, celli, basses, violins_trem, celli_trem, violins_spic,
  celli_spic, celli_pizz, solo_violin, harp
- winds and brass: flute, clarinet, oboe, horns, trombone, tuba, trumpet
- keys and organ: organ_loud, organ_pedal, organ_quiet, organ_flute4, organ_8, piano
- mallets: vibes, vibes_bowed, marimba, glock
- voices: `choir` (the choir_male ensemble), `voice` (the solo singer)
- other: guitar_clean
- GM-keyed drums:
  - `drumkit`: a real acoustic kit. 36 kick, 38 snare, 42/44/46 hats, 49 crash, 51 ride,
    45/47/48 toms.
  - `world_perc`: 48–50 cajon, 51–53 bongo, 54–56 shaker, 57–58 tambourine, 67–68 maracas,
    69 doum, 70 tak, 71 pa.

**Kits (one-shot files):**
- `catalog.kit(name, "glob*")` returns file paths for `s.hit`. Some kits keep their sfz
  programs separately; when a folder has no loose one-shots, play the kit through its
  GM-keyed sfz entry with `s.note` instead.
- VCSL/VSCO percussion folders (timpani hits, gongs, bass drums, cymbals) are `kit`
  entries. Find them with `search`. Long samples such as the 26 s timpani rolls must be
  trimmed: load with `engine.load(path)[0]`, slice, fade, then place with `s.audio`.

## Ensembles from one recorded performer

`rule = "ensemble"` entries (in `musicengine/catalog_data/ensembles.toml`) stack one
recorded performer into a section with `engine.Ensemble`. Each voice plays the recording of a
neighbouring note, pitched to the target, with small onset, tuning and pan offsets.
Parameters: `voices`, `detune_cents`, `spread_s`, `donors`, `attack`, `release`, `lo`/`hi`.
This is how `choir` is built. Stay inside `lo`–`hi`: past the recorded range the pitch shift
becomes audible.

## Synth patches: synth-style pieces only

Only for the synth cases, with a plan.json `"synth"` reason.
- Fine in synth cases:
  - leads: saw-lead, square-lead, supersaw, sine-lead
  - basses: acid-bass, sub-bass, reese-bass, synth-bass, wobble-bass, fm-bass
  - pads and others: warm-pad, glass-pad, synth-strings, synth-brass, pluck-synth
  - chip: chip-pulse, chip-square, chip-triangle
  - FM: e-piano, wurli, fm-bell
  - drums: `synth/drum-machine-808`, `synth/drum-machine-909`
  - the FreePats synth sets
- Avoid in every piece: the patches that imitate acoustic instruments (the world plucks,
  nylon-pluck, harp-synth, clav, organ-*, choir-*/voice-solo-*, celesta, music-box,
  tubular-bell, glass-harmonica, the winds) whenever a recording of that instrument exists;
  they are convincing in a mix but are not recordings.

The patches are plain oscillators until mixed. Give leads and pads chorus, delay and
reverb, sidechain pads and basses to the kick, and layer recordings where they fit.

## MIDI

```python
from musicengine import midi
midi.export_score(s, "out/name.mid")                  # or s.render(..., midi=True)
song = midi.read("in.mid")                            # notes in seconds, bpm, track names
midi.render_midi("in.mid", "out/name", drums="drumkit",          # or "acoustic", "808", "909"
                 overrides={"Lead": "violins", "ch2": "celli",
                            "prog33": "karoryfer-black-and-blue-basses/05-darkblack-pluck"})
```

All 128 GM programs map to catalog instruments (`midi.GM_PROGRAMS`), and channel 10 maps to
drums. The GM synth programs map to synths, so render_midi refuses them. Override every
such track with a recorded instrument, or pass `allow_synth=True` when the MIDI is a synth
piece (same rule as above).

## Project-specific instruments

`catalog.register(name, factory, library, license, credit)` defines a name for one project.
It takes precedence over the catalog for that name. The license must still be CC0 or
Unlicense, and the source must be a recording. New libraries for everyone go into
`musicengine/catalog_data/libraries.toml`, only after reading their license files.

## External renderers

SFZ programs that rely on loop points, offsets, filters or CC crossfades are rendered per note
through `sfizz_render` (and a General MIDI SoundFont would go through `fluidsynth`). The tool
is found through `MUSICENGINE_SFIZZ_RENDER` / `MUSICENGINE_FLUIDSYNTH`, then PATH; on
Windows the pinned upstream release is downloaded once and checked by SHA-256. Without sfizz,
those programs fall back to the built-in SFZ reader with a printed warning, or fail with
install hints when the reader cannot play them at all.
