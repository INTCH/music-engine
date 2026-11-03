"""Generate musicengine/catalog_data/generated/*.toml from the pinned source trees (needs `gh` logged in).

  python -I scripts/build_catalog.py         # rebuild instrument lists from libraries.toml
  python scripts/build_catalog.py --sfzorg   # also (re)pin every commercially usable
                                             # sfzinstruments repo at its current HEAD

Leaf folders with audio become instruments. The rule is decided from file names:
note names -> 'name' (octave offset measured at fetch), numbers -> 'number', neither -> 'kit'
(unpitched one-shots). Each .sfz program in an sfz library becomes an instrument.
"""
import json
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from musicengine.engine import parse_root  # noqa: E402

CAT = REPO / "musicengine" / "catalog_data"
GEN = CAT / "generated"
AUDIO = (".wav", ".flac", ".ogg")
USABLE = {"CC0-1.0", "Unlicense"}       # public-domain dedications only (see libraries.toml)
# Readmes reviewed by hand whose non-CC0 wording does not cover the audio.
FREEPATS_REVIEWED = {
    "world-percussion": ["README.txt"],   # CC-BY 4.0 applies only to picture.jpg; samples are CC0
}
SKIP_SFZ_REPOS ={"sfztemplates", "sfzinstruments.github.io", "mappings"}

FAMILY_WORDS = [
    ("strings", r"violin|viola|cello|contrabass|double.?bass|string|erhu|fiddle"),
    ("guitar", r"guitar|banjo|ganjo|mandolin|strumstick|lute|zither|cithara|lapharp|dan tranh|psaltery"),
    ("bass", r"bass(?!oon|.?drum|.?clar|.?recorder)"),
    ("keys", r"piano|organ|harpsichord|clav|rhodes|celest|tx81z|e-piano|epiano"),
    ("woodwinds", r"flute|piccolo|oboe|clarinet|bassoon|recorder|ocarina|sax|whistle|harmonica|krumhorn|shofar|didgeridoo|pipes"),
    ("brass", r"horn|trumpet|trombone|tuba"),
    ("mallets", r"vibraphone|vibes|marimba|xylo|glock|kalimba|mbira|balafon|chime|bells|steel.?drum|nyunga|crotal"),
    ("harp", r"harp"),
    ("drums", r"drum|snare|kick|tom|kit|cajon|conga|bongo|timpani|cymbal|hat|gong|perc|shaker|tamb|clap|cabasa|triangle|claves|cowbell|guiro|anvil|ratchet|agogo|slapstick|flexatone"),
    ("voice", r"vocal|voice|choir|chorus"),
    ("fx", r"alien|zap|siren|fx|misc|glass"),
]
SUSTAIN_WORDS = r"sus|sustain|vib|trem|legato|long|bowed|organ|loud|quiet|pedal|harmonica|ocarina|recorder|glasses|\d+'|full"


def family(path):
    p = path.lower()
    for fam, rx in FAMILY_WORDS:
        if re.search(rx, p):
            return fam
    return "other"


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)


def tree(owner_repo, sha):
    return [t["path"] for t in gh(f"repos/{owner_repo}/git/trees/{sha}?recursive=1")["tree"] if t["type"] == "blob"]


def q(s):
    return json.dumps(s, ensure_ascii=False)


def entry(**kw):
    lines = ["[[instrument]]"]
    for k, v in kw.items():
        if v is None:
            continue
        lines.append(f"{k} = {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def folder_instruments(lib, short):
    owner_repo = re.sub(r"^https://github.com/|\.git$", "", lib["git"])
    files = tree(owner_repo, lib["commit"])
    by_dir = defaultdict(list)
    for f in files:
        if f.lower().endswith(AUDIO):
            by_dir[f.rsplit("/", 1)[0] if "/" in f else ""].append(f.rsplit("/", 1)[-1])
    out = []
    for d, names in sorted(by_dir.items()):
        named = sum(parse_root(n) is not None for n in names)
        numbered = sum(bool(re.search(r"_\d+(?:_rr\d+)?\.\w+$", n)) for n in names)
        rule = "name" if named >= 0.6 * len(names) else ("number" if numbered >= 0.8 * len(names) and len(names) >= 6 else "kit")
        ext = max({n.rsplit(".", 1)[-1].lower() for n in names}, key=lambda e: sum(n.lower().endswith(e) for n in names))
        out.append(entry(
            name=f"{short}/{slug(d)}", library=lib["id"], path=d, files=f"*.{ext}", rule=rule,
            family=family(d), sustain=bool(re.search(SUSTAIN_WORDS, d.lower())) if rule != "kit" else None,
            count=len(names)))
    return out


def sfz_instruments(lib, short, files=None):
    owner_repo = re.sub(r"^https://github.com/|\.git$", "", lib["git"])
    files = files or tree(owner_repo, lib["commit"])
    progs = [f for f in files if f.lower().endswith(".sfz")
             and not re.search(r"(^|/)(modules|includes|include|data|inc)/", f.lower())]
    stems = [slug(f.rsplit("/", 1)[-1][:-4]) for f in progs]
    out = []
    for f, s in zip(progs, stems):
        if stems.count(s) > 1:            # same program name in several folders
            s = slug(re.sub(r"(?i)^programs/", "", f[:-4]))
        out.append(entry(name=f"{short}/{s}", library=lib["id"], path="", sfz=f, rule="sfz",
                         family=family(lib["id"] + " " + f)))
    return out


# Extension point: no public-domain General MIDI SoundFont is in the catalog today. A library
# with scan = "gm" (one .sf2 file) would become one rule = "gm" instrument per program, played
# through FluidSynth (musicengine/external.py).
GM_PROGRAM_NAMES = ["acoustic-grand-piano", "bright-acoustic-piano", "electric-grand-piano", "honky-tonk-piano", "electric-piano-1", "electric-piano-2", "harpsichord", "clavinet", "celesta", "glockenspiel", "music-box", "vibraphone", "marimba", "xylophone", "tubular-bells", "dulcimer", "drawbar-organ", "percussive-organ", "rock-organ", "church-organ", "reed-organ", "accordion", "harmonica", "tango-accordion", "nylon-guitar", "steel-guitar", "jazz-guitar", "clean-guitar", "muted-guitar", "overdriven-guitar", "distortion-guitar", "guitar-harmonics", "acoustic-bass", "finger-bass", "pick-bass", "fretless-bass", "slap-bass-1", "slap-bass-2", "synth-bass-1", "synth-bass-2", "violin", "viola", "cello", "contrabass", "tremolo-strings", "pizzicato-strings", "orchestral-harp", "timpani", "string-ensemble-1", "string-ensemble-2", "synth-strings-1", "synth-strings-2", "choir-aahs", "voice-oohs", "synth-voice", "orchestra-hit", "trumpet", "trombone", "tuba", "muted-trumpet", "french-horn", "brass-section", "synth-brass-1", "synth-brass-2", "soprano-sax", "alto-sax", "tenor-sax", "baritone-sax", "oboe", "english-horn", "bassoon", "clarinet", "piccolo", "flute", "recorder", "pan-flute", "blown-bottle", "shakuhachi", "whistle", "ocarina", "lead-square", "lead-sawtooth", "lead-calliope", "lead-chiff", "lead-charang", "lead-voice", "lead-fifths", "lead-bass-lead", "pad-new-age", "pad-warm", "pad-polysynth", "pad-choir", "pad-bowed", "pad-metallic", "pad-halo", "pad-sweep", "fx-rain", "fx-soundtrack", "fx-crystal", "fx-atmosphere", "fx-brightness", "fx-goblins", "fx-echoes", "fx-sci-fi", "sitar", "banjo", "shamisen", "koto", "kalimba", "bagpipe", "fiddle", "shanai", "tinkle-bell", "agogo", "steel-drums", "woodblock", "taiko-drum", "melodic-tom", "synth-drum", "reverse-cymbal", "guitar-fret-noise", "breath-noise", "seashore", "bird-tweet", "telephone-ring", "helicopter", "applause", "gunshot"]


def gm_instruments(lib, program_names):
    """One instrument per program of a public-domain General MIDI SoundFont (scan = "gm")."""
    out = []
    for prog, n in enumerate(program_names):
        out.append(entry(name=f"gm/{n}", library=lib["id"], rule="gm", program=prog,
                         family=family(n), tags=["general-midi", "fallback"]))
    return out


def main():
    GEN.mkdir(parents=True, exist_ok=True)
    libs = tomllib.loads((CAT / "libraries.toml").read_text(encoding="utf-8"))["library"]
    extra = CAT / "extra_libraries.toml"
    if extra.exists():
        libs += tomllib.loads(extra.read_text(encoding="utf-8")).get("library", [])
    for old in GEN.glob("*.toml"):
        if old.name not in ("sfzinstruments.toml", "freepats.toml"):
            old.unlink()
    for lib in libs:
        short = lib.get("short", slug(lib["id"]))
        if lib["scan"] == "folders":
            body = folder_instruments(lib, short)
        elif lib["scan"] == "sfz":
            body = sfz_instruments(lib, short)
        elif lib["scan"] == "gm":
            body = gm_instruments(lib, GM_PROGRAM_NAMES)
        else:
            continue
        (GEN / f"{slug(lib['id'])}.toml").write_text("# generated by scripts/build_catalog.py\n\n" + "\n".join(body), encoding="utf-8")
        print(f"{lib['id']}: {len(body)} instruments")

    for lib in libs:
        if lib["scan"] == "kits":                 # hand-written kit entries live in catalog_data/*.toml
            print(f"{lib['id']}: kits (hand-written)")

    if "--freepats" in sys.argv:
        repos = []
        page = 1
        while True:
            batch = gh(f"orgs/freepats/repos?per_page=100&page={page}")
            if not batch:
                break
            repos += batch
            page += 1
        have = {l["git"].rstrip("/").removesuffix(".git").lower() for l in libs if l.get("git")}
        lib_lines, body = ["# generated by scripts/build_catalog.py --freepats (CC0 repos only)\n"], []
        for r in sorted(repos, key=lambda r: r["name"].lower()):
            lic = (r.get("license") or {}).get("spdx_id")
            if lic not in USABLE or r["html_url"].lower() in have:
                continue
            sha = gh(f"repos/{r['full_name']}/commits/{r['default_branch']}")["sha"]
            lib = dict(id=f"freepats-{r['name']}", kind="git", git=r["clone_url"], commit=sha, license=lic,
                       credit=f"FreePats {r['name']} (CC0)", scan="sfz")
            if r["name"] in FREEPATS_REVIEWED:
                lib["license_reviewed"] = FREEPATS_REVIEWED[r["name"]]
            lib_lines.append("[[library]]\n" + "\n".join(f"{k} = {q(v)}" for k, v in lib.items()) + "\n")
            items = sfz_instruments(lib, slug(f"freepats-{r['name']}"), tree(r["full_name"], sha))
            body += items
            print(f"{r['name']}: {lic}, {len(items)} programs")
        (CAT / "freepats_libraries.toml").write_text("\n".join(lib_lines), encoding="utf-8")
        (GEN / "freepats.toml").write_text("# generated by scripts/build_catalog.py --freepats\n\n" + "\n".join(body), encoding="utf-8")

    if "--sfzorg" in sys.argv:
        repos = []
        page = 1
        while True:
            batch = gh(f"orgs/sfzinstruments/repos?per_page=100&page={page}")
            if not batch:
                break
            repos += batch
            page += 1
        lib_lines, body = ["# generated by scripts/build_catalog.py --sfzorg (CC0 / Unlicense repos only)\n"], []
        for r in sorted(repos, key=lambda r: r["name"].lower()):
            lic = (r.get("license") or {}).get("spdx_id")
            if lic not in USABLE or r["name"] in SKIP_SFZ_REPOS:
                continue
            sha = gh(f"repos/{r['full_name']}/commits/{r['default_branch']}")["sha"]
            lib = dict(id=r["name"], kind="git", git=r["clone_url"], commit=sha, license=lic,
                       credit=f"{r['name']} - sfzinstruments ({lic})", scan="sfz")
            lib_lines.append("[[library]]\n" + "\n".join(f"{k} = {q(v)}" for k, v in lib.items()) + "\n")
            files = tree(r["full_name"], sha)
            items = sfz_instruments(lib, slug(r["name"]), files)
            body += items
            print(f"{r['name']}: {lic}, {len(items)} programs")
        (CAT / "sfzinstruments_libraries.toml").write_text("\n".join(lib_lines), encoding="utf-8")
        (GEN / "sfzinstruments.toml").write_text("# generated by scripts/build_catalog.py --sfzorg\n\n" + "\n".join(body), encoding="utf-8")


if __name__ == "__main__":
    main()
