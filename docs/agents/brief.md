# Understanding a music request

Goal: leave this step with concrete numbers and names (tempo, meter, key/mode, form, length,
instrument list with roles, energy curve, deliverables). Adjectives are not a plan.

## Use decides form

| Use | Form | Typical length | Notes |
|---|---|---|---|
| Menu / title | seamless loop | 1:30–3:00 | Main theme stated clearly; starts and ends at similar energy |
| Exploration / ambient gameplay | seamless loop | 2:00–4:00 | Low density, no strong downbeats that tire; long harmonic rhythm |
| Combat / action | loop, often with intensity layers (stems) | 1:00–2:30 | Driving ostinato, percussion, short phrases; render stems for adaptive mixing |
| Boss | loop with intro | 1:30–3:00 | Signature motif, heavier low end, more dissonance |
| Victory / defeat / level-up | stinger | 2–8 s | One gesture: a cadence, a rising arpeggio, a falling minor line |
| Cutscene / trailer / reveal | one-shot cue | to picture | An arc with hit points; vast dynamic range is fine |
| Menu click / UI | one-shot | < 1 s | Usually not music. Say so |
| Song / track for listening | one-shot | 2:30–4:00 | Intro, verse, chorus, bridge, outro; development matters |
| Background for video/app | loop or one-shot | as asked | Stay out of the way of voice-over: mid range sparse |

Loops: the last bar must lead back into the first, harmonically (end on V or a chord that
moves to bar 1) and in energy. The engine wraps reverb and note tails across the seam
automatically.

## Mood to music

| Mood | Mode / harmony | Melody | Rhythm / tempo | Color |
|---|---|---|---|---|
| Hopeful, uplifting | major, Lydian (#4), I–V–vi–IV, suspensions resolving up | rising contours, leaps of 4th/5th/6th | moderate 70–110, steady pulse | strings, horns, piano, glockenspiel sparkle |
| Wonder, vastness | Lydian, quartal chords, slow harmonic rhythm, pedal tones | few long notes, wide intervals | slow 60–80, long notes | organ, high strings, wine glasses, big reverb |
| Melancholy, nostalgic | minor, Dorian, i–VI–III–VII, maj7/add9 colors | stepwise falling lines, appoggiaturas | slow-mid | solo cello/oboe/piano, soft string pads |
| Tense, suspense | minor, Phrygian (b2), diminished, chromatic bass, clusters | small intervals, repeated notes | ostinato 8ths/16ths, irregular hits | low strings tremolo, pulses, drones, timpani |
| Epic, heroic | minor→relative major, i–VI–III–VII, power fifths | bold rhythmic motif, octave doublings | 80–140, strong downbeats | brass, choir, big drums, full strings |
| Dark, menacing | Phrygian, Locrian, tritones, low clusters | short motif, half steps | slow heavy or fast driving | low brass, contrabass, distorted guitar, big drums |
| Playful, whimsical | major, chromatic passing tones, staccato | bouncy leaps, grace notes | 100–140, swing optional | pizzicato, clarinet, bassoon, marimba, glock |
| Calm, peaceful | major/pentatonic, plagal (IV–I), no dominant pull | slow, consonant | 60–80 or no pulse | pads, harp, flute, soft piano/vibes |
| Mysterious | whole-tone, Dorian, Lydian-b7, ambiguous chords | fragments, unresolved | free or slow | bowed vibes, harp harmonics, glass, choir |
| Energetic, fun | major/Mixolydian, I–bVII–IV | catchy riff, repetition | 120–175 | drums prominent, bass riffs, guitars (or synths in synth styles) |
| Romantic | major with secondary dominants, 9ths | wide lyrical lines | rubato feel, 60–90 | strings, piano, horn |

## Genre conventions

Engine names for the instruments are in [engine.md](engine.md). Synth sounds are listed only
where the genre is synth-native (see the recordings rule in [../../AGENTS.md](../../AGENTS.md)).

| Genre | Tempo | Meter / feel | Core instruments | Harmony | Drums / rhythm | Production |
|---|---|---|---|---|---|---|
| Orchestral cinematic | 60–140 | 4/4, 3/4, 6/8 | strings, horns, trumpet, trombone, tuba, timpani, harp, woodwinds, choir | functional or modal; pedals | timpani, bass drum, cymbal swells | hall reverb, wide strings |
| Hybrid trailer | 70–140 | 4/4 | strings ostinato, brass, choir, a synth pulse as a named colour, big drums | minor modal, i–VI–VII | big hits, risers, sidechain pulse | heavy compression, sub |
| Ambient / drone | free–80 | none | string pads, bowed vibes, glass, organ, drones | static, slow changes | none or sparse | long reverb, slow filter sweeps |
| Synthwave / retrowave | 80–118 | 4/4 straight | supersaw, synth bass (8ths), saw lead, gated snare | minor, i–VI–III–VII | 808/909 or drumkit, snare on 2/4 | chorus, delay, big reverb |
| House | 118–128 | four-on-the-floor | 909 kit, acid/synth bass, stabs, e-piano | minor 7th loops | kick every beat, offbeat open hat, clap 2/4 | sidechain duck on bass/pads |
| Techno | 125–140 | 4/4 | 909 kit, acid bass, minimal stabs | one or two chords | relentless kick, 16th hats | filter sweeps, delay |
| Drum & bass | 165–178 | breakbeat | drumkit (fast break), reese/sub bass, pads | minor | kick 1, snare 2/4, ghost notes | heavy sub, wide pads |
| Dubstep / trap | 140 (half-time 70) | half-time | 808 kick, hat rolls, wobble/sub bass | minor | snare on 3, hat 16th/32nd rolls | distortion on bass |
| Lo-fi hip hop | 70–90 | swung 16ths | piano, nylon guitar, upright or electric bass, soft acoustic kit (e-piano and 808 if synth is wanted) | maj7/min9 ii–V | lazy kick/snare, swung hats | tape, bitcrush, low-pass |
| Future garage / downtempo | 110–130 (half-time) | 2-step swing | guitar with delay, pads, vibes, sub | min9, bittersweet | skippy kicks, snare on 3 | sidechain, reverb, delay |
| Pop | 90–128 | 4/4 | piano/guitar, bass, drumkit, pads | I–V–vi–IV etc. | backbeat 2/4 | compressed, bright |
| Rock | 100–160 | 4/4 | guitars through the `amp` fx, bass, drumkit, organ | power chords, I–bVII–IV | backbeat, crash on 1 of sections | amp sim, double-tracked guitars hard L/R |
| Metal | 90–220 | 4/4, odd | guitars amp "metal", bass, double kick | Phrygian/Aeolian riffs | double kick 16ths, blast beats | tight, scooped mids |
| Jazz (swing) | 100–240 | swung 8ths | piano rootless voicings, upright bass walking, ride, sax/trumpet | ii–V–I, 7ths/9ths/13ths | ride "ding ding-ga-ding", hat 2/4 | room reverb, little compression |
| Bossa nova | 120–140 | straight 8ths | nylon guitar, upright bass, light drums, flute | maj7/min7, chromatic ii–V | syncopated guitar, rim clicks | intimate |
| Funk | 95–115 | 16th groove | electric bass, guitar chops, organ, brass stabs | dominant 7/9 vamps | tight 16ths, ghost snares | dry, punchy |
| Reggae | 70–90 | offbeat | organ "bubble", guitar skank on 2&4 offbeats, bass | I–IV–V | one-drop (kick+snare on 3) | spring-ish reverb, delay |
| Folk / acoustic | 70–130 | 4/4, 3/4, 6/8 | acoustic/nylon guitar, banjo, fiddle (solo violin), accordion | diatonic | light percussion, shakers | natural, little fx |
| Celtic | 90–180 | 6/8 jig, 4/4 reel | fiddle, flute/whistle, bagpipe, harp, low tom for bodhran | Dorian/Mixolydian | driving 6/8 | dry-ish |
| Chiptune | 120–180 | 4/4 | chip pulse/square lead, chip triangle bass, noise drums + bitcrush | major/minor, arpeggiated chords | fast hats, simple kick/snare | no reverb, bitcrush |
| East Asian | 60–100 | free/4/4 | zithers, erhu, flutes, big bass drum | pentatonic (in, yo, gong) | sparse big drums | reverb, space |
| Indian | 70–140 | tala (teental 16) | bansuri-like flute, tabla, a drone | raga (e.g. Bhairav, Yaman) over drone | tabla theka | drone throughout |
| Middle Eastern | 80–120 | maqsum, saidi | darbuka (world_perc), hammered dulcimer, winds | maqam (Hijaz, Nahawand) | doum-tak patterns | reverb, ornamented lines |
| Latin | 90–130 | clave-based | nylon guitar, piano montuno, bass tumbao, congas/bongos (world_perc), brass | ii–V, minor vamps | clave 3-2/2-3 | dry, bright |
| Choral / sacred | 50–80 | free | choir, organ | functional, suspensions | none | long reverb |
| Horror | free | none | low strings, clusters, bowed vibes, glass, voice | atonal, clusters, tritones | irregular hits | extreme dynamics, silence |

Some world instruments (sitar, koto, oud, shamisen, duduk...) exist in the catalog only as
synthesized stand-ins. In a recordings-only piece, use a recorded relative or say what is
missing; check with `python -m musicengine search`.

## Reading a free-text prompt or a reference

1. Extract hard values: BPM, meter, key, length, and any instruments named.
2. Turn every adjective into a decision using the tables above, and write it down.
3. List the instruments named. Map each one to a catalog name, or mark it as synth-only or
   unavailable. Say what you substitute.
4. Turn arc words ("begins with", "suddenly", "gradually blooms", "resolves") into sections
   with bar counts.
5. For a named reference work, take the techniques that define its sound: an organ with
   minimalist repetition, clock-like ostinati, a vocal drone, sparse low strings. Never take
   its melodies.
6. For a reference *file* (a local audio file the user provides; never download one), run
   `python -m musicengine reference <file> <track dir>/reference.json` and use the measured
   tempo, key, loudness, tonal balance, width, density and section times.

## Questions worth asking (only when the answer changes the plan)

Batch these, give each a recommended default, and skip any the request already answers.
- Where and how will it be used? This decides loop vs one-shot, length and stems.
- Which instrument should lead? Is there one to avoid?
- How dense should it be: sparse and spacious, or full?
- Background textures (noise, air, vinyl crackle): wanted, or not?
- Should it follow a given key or tempo, to match other tracks or a video cut?
- Deliverables: WAV/OGG only, or stems and/or MIDI too?
