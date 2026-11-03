"""The instrument catalog: find instruments, fetch them on first use, build playable objects,
and remember which ones a render used (for credits and the render sidecar).

    from musicengine import catalog
    catalog.search("cello")                  # -> names
    violins = catalog.get("violins")         # alias or full name; downloads if missing
    hits = catalog.kit("vsco/percussion-timpani", "*Hit_v3*")   # one-shot sample paths
"""
import fnmatch
import glob
import json
import tomllib
from pathlib import Path

from . import fetch
from .calibrate import calibrate, number_of
from .config import LIBRARY, CATALOG_DIR, ALLOWED_LICENSES
from .engine import Instrument, parse_root, parse_layer

_LIBS, _INST, _ALIAS = {}, {}, {}
_SYNTHETIC = {"libraries": set(), "names": []}   # catalog_data/synthetic.toml
USED = {}            # name -> entry, for credits/sidecars
_BUILT = {}


def _load():
    if _INST:
        return
    files = sorted(CATALOG_DIR.glob("*.toml")) + sorted((CATALOG_DIR / "generated").glob("*.toml"))
    overrides = []
    for f in files:
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        overrides += data.get("override", [])
        for lib in data.get("library", []):
            if lib["license"] not in ALLOWED_LICENSES:
                raise ValueError(f"{f.name}: library {lib['id']} has disallowed license {lib['license']}")
            _LIBS[lib["id"]] = lib
        for e in data.get("instrument", []):
            if e["name"] in _INST:
                raise ValueError(f"duplicate instrument name {e['name']} ({f.name})")
            _INST[e["name"]] = e
        for a in data.get("alias", []):
            _ALIAS[a["name"]] = a
        syn = data.get("synthetic", {})
        _SYNTHETIC["libraries"].update(syn.get("libraries", []))
        _SYNTHETIC["names"] += syn.get("names", [])
    for o in overrides:              # catalog_data/overrides.toml: hand settings for generated entries
        if o["name"] not in _INST:
            raise ValueError(f"override for unknown instrument {o['name']!r}")
        _INST[o["name"]].update({k: v for k, v in o.items() if k != "name"})
    _add_synth_entries()


def synthetic_path(path):
    """synthetic() for a one-shot file (from kit()), by the library folder it lives in."""
    _load()
    p = Path(path).resolve()
    try:
        rel = p.relative_to(LIBRARY.resolve())
    except ValueError:
        return None                              # outside the library: a project's own file
    if rel.parts[0] == "_synth":
        return "file rendered by the built-in synth"
    for lib_id, lib in _LIBS.items():
        if rel.parts[0] == lib_id and lib_id in _SYNTHETIC["libraries"]:
            return f"library {lib_id} is synthesized"
    for n, e in _INST.items():
        if e.get("rule") != "kit" or not any(fnmatch.fnmatch(n, pat) for pat in _SYNTHETIC["names"]):
            continue
        folder = (LIBRARY / e["library"] / e.get("path", "")).resolve()
        if p.parent == folder and fnmatch.fnmatch(p.name, e.get("files", "*")):
            return f"{n} is a synthetic source"
    return None


def synthetic(name):
    """Why `name` is not a recording of a real instrument, or None when it is.
    Follows aliases and ensembles down to the source they play."""
    _load()
    if name in _LOCAL:
        e = _LOCAL[name][1]
    else:
        e = entry(name)
    if e.get("rule") == "ensemble":
        return synthetic(e["of"])
    if e["library"] in _SYNTHETIC["libraries"]:
        return f"library {e['library']} is synthesized"
    for n in (name, e["name"], e.get("alias_of", "")):
        for pat in _SYNTHETIC["names"]:
            if n and fnmatch.fnmatch(n, pat):
                return f"{n} matches synthetic source {pat!r}"
    return None


SYNTH_FAMILY = {"subtractive": "synth", "fm": "keys", "organ": "keys", "pluck": "guitar", "voice": "voice",
                "additive": "mallets", "wind": "woodwinds"}


def _add_synth_entries():
    """Every synth patch and drum machine becomes a catalog instrument (license Synthesized)."""
    from .synth import PATCHES
    for name, p in PATCHES.items():
        fam = SYNTH_FAMILY[p["engine"]]
        if "bass" in name:
            fam = "bass"
        _INST[f"synth/{name}"] = dict(name=f"synth/{name}", library="synth", rule="synth", patch=name,
                                     family=fam, tags=["synthesized", p["engine"]])
    for kit in ("808", "909"):
        _INST[f"synth/drum-machine-{kit}"] = dict(name=f"synth/drum-machine-{kit}", library="synth", rule="synthkit",
                                                 kit=kit, family="drums", tags=["synthesized", "electronic"])


def libraries():
    _load()
    return dict(_LIBS)


def entry(name):
    _load()
    if name in _ALIAS:
        a = _ALIAS[name]
        e = dict(_INST[a["instrument"]])
        e.update({k: v for k, v in a.items() if k not in ("name", "instrument")})
        e["alias_of"] = a["instrument"]
        e["name"] = name
        return e
    if name not in _INST:
        close = search(name.split("/")[-1])[:8]
        raise KeyError(f"unknown instrument {name!r}. Close: {close}")
    return dict(_INST[name])


def search(text="", family=None):
    """Names whose name/path/family match every word of text."""
    _load()
    words = text.lower().split()
    out = []
    for n, e in list(_ALIAS.items()) + list(_INST.items()):
        blob = " ".join(str(e.get(k, "")) for k in ("name", "instrument", "path", "sfz", "family", "tags")).lower() + " " + n
        if all(w in blob for w in words) and (family is None or e.get("family") == family
                                              or _INST.get(e.get("instrument", ""), {}).get("family") == family):
            out.append(n)
    return out


def license_of(e):
    _load()
    lib = _LIBS.get(e["library"], {})
    return e.get("license", lib.get("license")), e.get("credit", lib.get("credit"))


def _ensure(e):
    lib = _LIBS[e["library"]]
    if lib["kind"] == "builtin":
        return None
    if lib["kind"] == "file":
        return fetch.ensure_file(lib)
    return fetch.ensure_git(lib, [e.get("path", "")])


def _files(e):
    root = LIBRARY / e["library"] / e["path"]
    pat = e.get("files", "*.wav")
    return [f for f in sorted(glob.glob(str(root / pat))) if Path(f).is_file()]


def _calibration(e, files):
    """Measured once per folder, stored next to the samples. An explicit `offset` in the
    catalog entry wins: the detector makes octave errors on some sounds (mixture organ stops,
    bells), and a value verified by analysis of real renders is better than a re-measurement."""
    if "offset" in e:
        return e["offset"]
    store = LIBRARY / e["library"] / ".calibration.json"
    cal = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    key = f"{e['path']}|{e['rule']}|{e.get('include', '*')}"
    if key not in cal:
        c = calibrate(files, e["rule"])
        cal[key] = c
        store.write_text(json.dumps(cal, indent=1), encoding="utf-8")
        print(f"[calibrate] {e['name']}: offset {c['offset']} (agree {c['agree']:.0%} of {c['probed']})")
    c = cal[key]
    if c["offset"] is None:
        raise ValueError(f"{e['name']}: could not measure pitches")
    if c["agree"] < 0.6:
        print(f"[warn] {e['name']}: only {c['agree']:.0%} of probed samples agree on the root offset; "
              "check with `python -m musicengine check` before trusting pitches")
    return c["offset"]


def _sfz_octave(e, zones):
    """Some SFZ maps sound an octave away from their keys (e.g. a male voice mapped up).
    Measure the mapped samples once; returns the octave shift (multiple of 12) that makes
    note numbers mean sounding pitch. Unpitched maps (keytrack off) -> 0."""
    pitched = [z for z in zones if z["keytrack"]]
    if len(pitched) < 3:
        return 0
    store = LIBRARY / e["library"] / ".calibration.json"
    cal = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    key = f"sfz|{e['sfz']}|{e.get('articulation')}"
    if key not in cal:
        from .calibrate import detect_midi
        roots = sorted({z["root"] for z in pitched})
        probe = roots[len(roots) // 4: len(roots) * 3 // 4 + 1:max(1, len(roots) // 6)][:6]
        diffs = []
        for r in probe:
            zz = next(z for z in pitched if z["root"] == r)
            try:
                diffs.append(detect_midi(zz["path"]) - r - zz["tune_cents"] / 100)
            except Exception:
                pass
        best = (0.0, 0)
        for c in (-24, -12, 0, 12, 24):
            agree = sum(abs(d - c) < 0.6 for d in diffs) / max(1, len(diffs))
            best = max(best, (agree + (0.01 if c == 0 else 0), c))
        octave = best[1] if best[0] >= 0.6 else 0      # only trust a clear majority
        cal[key] = dict(octave=octave, agree=round(best[0], 2), probed=len(diffs))
        store.write_text(json.dumps(cal, indent=1), encoding="utf-8")
        if octave:
            print(f"[calibrate] {e['name']}: map sounds {octave:+d} semitones from its keys; corrected")
    return cal[key]["octave"]


ENVELOPE_KEYS = ("sustain", "attack", "release", "gain", "keep_level", "tune", "smooth_layers", "speak")


_LOCAL = {}


def register(name, factory, library, license, credit, path=""):
    """A project-local instrument definition (takes precedence over the catalog for `name`).
    factory() -> Instrument. The license is still checked against the allowlist."""
    from .config import ALLOWED_LICENSES as ok
    if license not in ok:
        print(f"[warn] {name}: license {license} is outside the catalog allowlist")
    _LOCAL[name] = (factory, dict(name=name, library=library, path=path, license=license, credit=credit))


def get(name):
    """A playable instrument (engine.Instrument or external.ExternalInstrument)."""
    if name in _LOCAL and name not in _BUILT:
        factory, e = _LOCAL[name]
        _BUILT[name] = (factory(), e)
    if name in _BUILT:
        USED[name] = _BUILT[name][1]
        return _BUILT[name][0]
    e = entry(name)
    if e["rule"] == "kit":
        raise TypeError(f"{name} is a set of unpitched one-shots; use catalog.kit({name!r})")
    if e["rule"] == "ensemble":
        from .engine import Ensemble
        opts = {k: e[k] for k in ("voices", "detune_cents", "spread_s", "donors", "attack", "release", "lo", "hi")
                if k in e}
        inst = Ensemble(name, get(e["of"]), **opts)
        _BUILT[name] = (inst, e)
        USED[name] = e
        return inst
    _ensure(e)
    env = {k: e[k] for k in ENVELOPE_KEYS if k in e}
    rule = e["rule"]
    if rule in ("name", "number"):
        files = _files(e)
        if "include" in e:
            files = [f for f in files if fnmatch.fnmatch(Path(f).name, e["include"])]
        off = _calibration(e, files)
        if rule == "name":
            root_fn = lambda f: (lambda r: None if r is None else r + off)(parse_root(f))  # noqa: E731
        else:
            root_fn = lambda f: (lambda n: None if n is None else n + off)(number_of(f))  # noqa: E731
        layer_fn = parse_layer
        if e.get("layers") == "soft":
            layer_fn = lambda f: 0 if "_soft" in f else 1  # noqa: E731
        zones = [(f, root_fn(f), layer_fn(f)) for f in files if root_fn(f) is not None]
        if not zones:
            raise FileNotFoundError(f"{name}: no usable samples in {LIBRARY / e['library'] / e['path']}")
        inst = Instrument(name, zones, **env)
    elif rule == "sfz":
        from . import sfz as sfzmod
        from .external import ExternalInstrument, sfizz_available
        path = LIBRARY / e["library"] / e["sfz"]
        z, ignored = sfzmod.zones(str(path), articulation=e.get("articulation"), report=True,
                                  lib_root=str(LIBRARY / e["library"]))
        backend = e.get("backend") or ("sfizz" if ignored & sfzmod.NEEDS_SFIZZ and sfizz_available() else "python")
        octave = _sfz_octave(e, z)
        if backend == "sfizz" or not z:
            inst = ExternalInstrument(name, "sfizz", str(path), transpose=-octave,
                                      velocity_curve=e.get("velocity_curve", False))
            if z:   # playable range, for checks and for callers that want to stay in range
                import numpy as _np
                inst.roots = _np.array(sorted({k + octave for zz in z for k in (zz["lokey"], zz["hikey"])
                                               if 0 <= k <= 127}))
        else:
            for zz in z:
                zz["root"] += octave
                if zz["lokey"] != zz["hikey"] or zz["keytrack"]:
                    zz["lokey"] += octave
                    zz["hikey"] += octave
            inst = Instrument(name, z, **env)
    elif rule == "synth":
        from .synth import SynthInstrument
        inst = SynthInstrument(name, e["patch"])
        for k in ("release",):
            if k in e:
                inst.patch["release"] = e[k]
    elif rule == "gm":
        from .external import ExternalInstrument
        sf2 = LIBRARY / e["library"] / _LIBS[e["library"]]["filename"]
        inst = ExternalInstrument(name, "fluidsynth", str(sf2), program=e["program"], drums=e.get("drums", False))
    else:
        raise ValueError(f"{name}: unknown rule {rule}")
    _BUILT[name] = (inst, e)
    USED[name] = e
    return inst


def kit(name, pattern="*"):
    """Paths of one-shot samples in a kit folder, filtered by a filename glob.
    Raises (naming the pattern) when nothing matches - an empty list would only fail later."""
    e = entry(name)
    if e["rule"] == "synthkit":
        from .synth import drum_kit_files
        files = [f for f in drum_kit_files(e["kit"], LIBRARY / "_synth" / f"drum-machine-{e['kit']}")
                 if fnmatch.fnmatch(Path(f).name, pattern)]
        if not files:
            raise FileNotFoundError(f"{name}: no hits match {pattern!r}")
        USED[name] = e
        return files
    _ensure(e)
    files = [f for f in _files(e) if fnmatch.fnmatch(Path(f).name, pattern)]
    if not files:
        raise FileNotFoundError(f"{name}: no files match {pattern!r} in {LIBRARY / e['library'] / e['path']}")
    USED[name] = e
    return files


def credits(names=None):
    """Credit lines for the given (or all used) instruments, one per library/credit."""
    _load()
    names = names or list(USED)
    lines = []
    for n in names:
        e = USED.get(n) or entry(n)
        lic, credit = license_of(e)
        if credit not in lines:
            lines.append(credit)
    return lines


def provenance():
    """What a render depended on: instruments, their library commits, licenses."""
    _load()
    out = {}
    for n, e in USED.items():
        lib = _LIBS.get(e["library"], {})
        out[n] = dict(library=e["library"], commit=lib.get("commit") or lib.get("sha256"),
                      path=e.get("path") or e.get("sfz"), license=license_of(e)[0])
    return out
