# Composition and arrangement craft

Use this to fill in the plan: form, harmony, motifs, voicing, ranges, orchestration, and how
the arrangement moves. It is written for code-composed music, where every note is placed
deliberately. Nothing happens by accident, so nothing should be left to chance either.

## Form templates (bars at 4/4)

- **Loop, 2–3 min:** A(8) A'(8) B(8) peak(8) breakdown(8) A''(8). The last bar leads back
  to bar 1.
- **Layered loop (adaptive):** a single 16–32 bar cycle. All intensity layers play the
  same harmony, and stems let the game fade layers in and out.
- **One-shot cue:** intro → development → climax → resolution. Place climax hits on
  downbeats you can name ("bar 34").
- **Song:** intro(4–8) verse(8–16) pre(4) chorus(8–16) verse chorus bridge(8) chorus×2
  outro.
- **Stinger:** 1–4 bars and one gesture: a cadence (V–I, IV–I, bVI–bVII–I for heroic), an
  arpeggio sweep, or a cymbal swell into a hit.

Change something every 4–8 bars: add or remove a layer, change register, change rhythm
density, or reharmonize. Pure repetition without development reads as broken.

## Harmony

- **Chord rhythm.** Slow (1 chord per 2–4 bars) feels spacious, cinematic, ambient. Fast
  (2–4 per bar) feels busy, jazz, pop pre-chorus.
- **Useful progressions:**
  - i–VI–III–VII: epic minor
  - I–V–vi–IV: pop
  - vi–IV–I–V: emotional pop
  - i–iv–v / i–iv–VII: folk minor
  - ii–V–I: jazz
  - I–bVII–IV: rock / Mixolydian
  - i–bII: Phrygian menace
  - I–II (Lydian, over a tonic pedal): wonder
  - IV–I: plagal, gentle
  - i–VI–iv–V: dramatic minor with a leading tone
- **Pedal points.** Holding the bass on the tonic while chords change above it gives
  stability, tension or vastness. This is common in cinematic music.
- **Color tones**: add9, maj7, sus2/sus4, min9, 6/9. Use them on sustained chords, not on
  fast stabs.
- **Voice leading.** Move each upper voice by the smallest step. Keep common tones. Avoid
  parallel fifths and octaves in exposed orchestral writing (fine in rock and electronic).
- **Voicing.**
  - Open voicings (root + fifth low, third/7th/9th higher) sound bigger and clearer than
    close triads low down.
  - Below C3, use only roots, fifths and octaves; thirds turn to mud.
  - Spread the voices: wider gaps at the bottom, closer at the top.
- **Density cap.** At most about 4 distinct sustained pitch classes at once in sparse
  styles. Full tutti can double them across octaves.
- **Cadences mark sections**: V–I, IV–I, bVI–bVII–I, or a deceptive V–vi to keep going.

## Melody and motif

- A motif is 3–7 notes with a distinctive rhythm and one characteristic interval (a rising
  sixth, a falling minor second, a Lydian #4). Write it in the plan as notes with durations.
- Develop it rather than inventing new tunes:
  - repeat, sequence (transpose), invert, augment (longer notes)
  - fragment (first 2–3 notes), change the harmony under it, change the instrument or
    register
- **Contour.** Have one high point per phrase, arrive at it by step or by a leap that then
  turns back, and keep phrases 2, 4 or 8 bars long.
- **Breathing.** Leave rests. A lead that never stops makes the piece tiring.
- **Countermelody.** Move it in the lead's long notes, in contrary motion, in a different
  register.
- **Never reuse** existing copyrighted melodies. Check that a motif is not a famous tune by
  looking at its first 5 notes.

## Rhythm and groove

- **Ostinato** (a repeated figure) drives cinematic and minimalist music. Keep it to 1–2
  bars, and vary the accents rather than the notes.
- **Swing**: delay off-beat 8ths (jazz about 0.62–0.67 of the beat, lo-fi about 0.58–0.6).
  `examples/genre_demos.py` has a `swing()` helper.
- **Humanize.** `Score.note` has small timing jitter by default (`human=0.006` s). Use
  `human=0` for machine-tight electronic parts; vary velocity by ±0.05–0.15 on repeated
  notes.
- **Play the melody.** Write melodies with `Score.line`: slur what a player would slur
  (stepwise and lyrical lines), break the legato with a rest where they would breathe, and
  set the phrase's high note where the line should lead; the phrase shaping builds toward it.
  Give a long note a swell that matches where it goes: `cresc` into a climax, `dim` into a
  cadence, `fp` for an accented entrance that then holds.
- **Accents.** Groupings of 3 inside 4/4 (3+3+2) create forward motion without changing
  meter.

## Instrument ranges (sampled range; stay inside, prefer the middle)

| Name | Range | Sweet spot / role |
|---|---|---|
| violins | G3–D6 | melody and high pads; above E5 is bright and intense |
| violas | C3–D6 | inner harmony, warm middle |
| celli | C2–F5 | bass in quiet textures, singing melodies at C3–A4 |
| basses (contrabass) | E1–B3 | the foundation; doubles celli an octave below |
| solo_violin | G3–C7 | intimate solo lines |
| harp | E1–F7 | arpeggios, glissando-like runs, sparkle |
| flute | C4–C7 | airy melodies; weak below G4 |
| oboe | A#3–F6 | plaintive solos |
| clarinet | D3–F#6 | warm lines, playful staccato |
| horns | A1–F5 | warm melody (C3–C5), heroic doubling, soft pads |
| trumpet | F3–C6 | fanfares, heroic leads |
| trombone | A#1–F4 | power chords, low brass weight |
| tuba | F1–D4 | brass bass |
| piano | A#0–G#7 | everything; avoid chords below C3 |
| organ_loud / organ_quiet | C2–C7 | pads, ostinati, cathedral weight |
| organ_flute4 | C3–E7 | soft, pure ostinati |
| vibes | F3–E6 | soft mallet arps and chords |
| marimba | F2–C7 | rhythmic patterns, warm |
| glock | G5–C8 | sparkle on top; sparse |
| guitar_clean | C2–C#6 | arpeggios, chords, melodies with delay |
| choir | C2–D#4 (MIDI 36–63) | one recorded male singer stacked into a section; "a" vowel only |

Check any other instrument with `python -m musicengine check <name>`. Synths cover roughly
C1–C8, but the musical range is per patch. Drums are GM keys or kit files, not pitches.

## Orchestration and arrangement

- **Roles per section:** melody, countermelody, harmony/pad, bass, rhythm/ostinato, color.
  Not every role needs filling; sparse is often better.
- **Doubling for weight**:
  - melody: violins + flute an octave up, or horns in unison with celli
  - bass: celli + basses an octave lower
- **Register spacing.** Do not stack several instruments in the same octave doing
  different things, especially between C3 and C5. Separate them by register or by rhythm.
- **Builds**: add layers, raise the register, shorten note values (halves → quarters →
  8ths), open a filter, swell a cymbal, crescendo the velocities. Release by removing
  layers or by sudden silence.
- **Silence and space.** A bar of almost nothing before a peak makes the peak land.
- **Electronic:**
  - kick and bass must not fight: sidechain the bass to the kick, or keep the bass notes off
    the kick hits
  - pads go behind a high-pass filter
- **Mix roles (stem `level_db`, rough starting points):**

| Role | level_db |
|---|---|
| lead / melody | −19 to −21 |
| main harmony | −21 to −23 |
| bass | −20 to −22 |
| drums | −17 to −22 |
| pads / colors | −24 to −30 |
| quiet support (fragments, textures) | −29 to −34 |

- **Reverb send (stem `reverb`):**
  - dry genres (funk, chip, close mics): 0–0.15
  - pop and electronic: 0.15–0.3
  - orchestral: 0.35–0.5
  - ambient and choir: 0.5–0.7
- **Stereo.** Pan pairs (two guitars ±0.6). Keep bass and kick centered. Width above 1 only
  on pads and strings.

## Game-music specifics

- **Loops** start mid-texture after the first play, because the tail wraps into the start.
  Do not put a big intro hit on bar 1 unless the game plays the intro separately.
- **Adaptive stems.** Every layer must work alone and with any combination of the others.
  Keep the harmony identical across layers and the levels balanced, and render with
  `stems=True`.
- **Space for dialogue and SFX.** Leave the 1–4 kHz mid range sparse during dialogue; keep
  low end for explosions in mind.
- **Listener fatigue.** For music heard for 10+ minutes, avoid bright leads, sharp
  transients and constant high hats. Prefer long harmonic rhythm.
- **Matching set.** Tracks of one game share a palette (2–3 signature instruments) and
  related keys. A shared motif ties them together.
