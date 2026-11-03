# Several variants of a new track (optional)

An agent cannot hear which of several good plans sounds best; the person who asked can, in a
minute. When your harness supports sub-agents or parallel tasks, a new track can start as a
few (typically four) different, finished, verified renders, and the person picks one.

## When

- A new track, or "start over" on one.
- Not for changes to an existing track (tempo, mix, instrument swap, one section): those are
  one render of the picked version.
- Not when the person asks for one version, or for later tracks of a set whose direction is
  settled (reuse the palette and motif instead).

## 1. Brief and direction cards

Write the brief once (use, form, length, tempo range, key area, hard constraints, reference
numbers if a reference file was given). Then one direction card per variant that differ in
what matters most to the listener, all inside the brief's hard constraints:

| Axis | Examples |
|---|---|
| lead / palette | solo cello vs horns vs harp+flute vs piano trio |
| harmonic language | modal and static vs functional minor vs Lydian lift vs pedal + clusters |
| density / energy | sparse and spacious vs driving ostinato vs layered build |
| form / arc | slow build to one peak vs two contrasting halves vs steady state |

Vary at least two axes between any two cards; cards that differ only in instrument read as
one idea. Each card is 3-5 lines: the idea in one sentence, lead and palette, harmony, tempo
and feel, arc. Show the cards before starting when the piece is substantial.

## 2. Prepare, then fan out

1. Fetch every instrument the cards name first: `python -m musicengine fetch <names…>`.
   Fetches are locked per library, but one fetch up front avoids workers waiting on the
   same download.
2. Folders: `music/<track>/v1` … `v4`, one per worker. Workers never write outside their
   own folder.
3. Start the workers in parallel, each with the brief below.

## 3. Worker brief (fill in)

```
TASK: Compose and render variant <n> of "<track>" in music/<track>/v<n>/ following this direction.
BRIEF: <the shared brief>
DIRECTION: <this variant's card>
DO:
- Read AGENTS.md in the music-engine repo and follow its plan -> compose -> render -> verify
  steps, skipping docs/agents/variants.md.
- Write v<n>/plan.json (`plan check` must pass), v<n>/track.py (builds the Score with
  plan.score, fixed seed), render to v<n>/out/<track>.
- python -m musicengine verify v<n>/plan.json v<n>/out/<track>.wav: no FAIL. Fix and
  re-render until it passes; look at every WARN.
- Recordings only (synths only if plan.json has a "synth" reason), public-domain sources
  only, no copied melodies. Touch nothing outside v<n>/.
RETURN (max ~1500 characters): wav path, verify status with any WARN, the idea in one line,
lead/palette, key/tempo/length, and anything that may sound wrong despite good numbers.
```

## 4. Present

- Read each `verify.json` yourself; a variant that FAILs is fixed or dropped, not shown.
- Hand over the WAVs together, labelled v1-v4 with one line each (idea, lead, tempo). Say
  they were measured, not listened to.
- Ask which one to keep, and what to take from the others ("v2 but with v4's harp").
- After the pick, work on that folder only; leave the others until the person says to
  delete them.
