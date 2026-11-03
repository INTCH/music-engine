"""Minimal SFZ reader: turns an .sfz file into sample zones the Python sampler can play.

Covers what free libraries mostly use: <control>/<global>/<master>/<group>/<region> inheritance,
default_path, #define, #include, sample, key/lokey/hikey, pitch_keycenter, pitch_keytrack,
lovel/hivel, tune/transpose, volume, trigger (release-trigger regions are skipped), and
keyswitches (sw_last / sw_lokey..sw_hikey / sw_default) as a chosen articulation.
Anything else (CC crossfades, filters, LFOs) is ignored - for libraries that depend on those,
render the part through sfizz instead (external.render_sfizz).
"""
import os
import re

NOTE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
HEADER_RE = re.compile(r"<(\w+)>")
OPCODE_RE = re.compile(r"([A-Za-z0-9_]+)=")


def key_value(v):
    """SFZ key: a number, or a note name where c4 = 60."""
    v = v.strip().lower()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    m = re.fullmatch(r"([a-g])([#b]?)(-?\d+)", v)
    if not m:
        raise ValueError(f"bad key {v!r}")
    return NOTE[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)] + 12 * (int(m.group(3)) + 1)


DIRECTIVE_RE = re.compile(r'#define\s+(\$\w+)\s+([^\s]+)|#include\s+"([^"]+)"')


def _subst(text, defines):
    for k in sorted(defines, key=len, reverse=True):
        text = text.replace(k, defines[k])
    return text


def _read(path, defines, root_dir, depth=0):
    """Expand #define/#include in document order. The same file may be included many times
    (e.g. one region list per velocity layer, with $VEL redefined in between), and include
    paths are relative to the top-level .sfz, as sfizz resolves them."""
    if depth > 16:
        raise ValueError(f"#include nesting too deep at {path}")
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    out, pos = [], 0
    for m in DIRECTIVE_RE.finditer(text):
        out.append(_subst(text[pos:m.start()], defines))
        if m.group(1):
            defines[m.group(1)] = _subst(m.group(2), defines)
        else:
            inc = os.path.join(root_dir, _subst(m.group(3), defines).replace("\\", "/"))
            if os.path.exists(inc):
                out.append(_read(inc, defines, root_dir, depth + 1))
        pos = m.end()
    out.append(_subst(text[pos:], defines))
    return "\n".join(out)


def _opcodes(body):
    """'sample=a b.wav lokey=60' -> {'sample': 'a b.wav', 'lokey': '60'} (values may hold spaces)."""
    ops = {}
    marks = list(OPCODE_RE.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        ops[m.group(1)] = body[m.end():end].strip()
    return ops


def parse(sfz_path):
    """Returns (regions, control). Each region is a flat dict of inherited opcodes."""
    text = _read(sfz_path, {}, os.path.dirname(os.path.abspath(sfz_path)))
    parts = HEADER_RE.split(text)
    scope = {"control": {}, "global": {}, "master": {}, "group": {}}
    regions = []
    for i in range(1, len(parts), 2):
        header, body = parts[i].lower(), parts[i + 1]
        ops = _opcodes(body)
        if header == "region":
            r = {}
            for lvl in ("global", "master", "group"):
                r.update(scope[lvl])
            r.update(ops)
            regions.append(r)
        elif header in scope:
            scope[header] = dict(ops)
            # a new outer scope resets the inner ones
            order = ["control", "global", "master", "group"]
            for lvl in order[order.index(header) + 1:]:
                scope[lvl] = {}
        # <curve>, <effect>, <midi>, <sample> headers are ignored
    return regions, scope["control"]


SUPPORTED = {"sample", "key", "lokey", "hikey", "pitch_keycenter", "pitch_keytrack", "lovel", "hivel",
             "tune", "transpose", "volume", "trigger", "sw_last", "sw_lokey", "sw_hikey", "sw_default",
             "sw_label", "default_path", "seq_length", "seq_position"}
# opcodes whose absence changes the sound a lot: if a file relies on them, prefer sfizz
NEEDS_SFIZZ = {"loop_start", "loop_end", "loop_mode", "offset", "end", "xfin_locc1", "xfout_locc1",
               "xfin_lovel", "xfout_lovel", "xfin_hivel", "xfout_hivel"}


def zones(sfz_path, articulation=None, report=False, lib_root=None):
    """report=True -> (zones, ignored_opcodes)."""
    z = _zones(sfz_path, articulation, lib_root)
    if not report:
        return z
    regions, control = parse(sfz_path)
    used = set(control)
    for r in regions:
        used |= set(r)
    ignored = {k for k in used if k not in SUPPORTED and not CC_RANGE_RE.match(k)
               and not k.startswith(("label", "region_label", "group_label", "master_label", "set_",
                                     "amp_veltrack", "ampeg_", "pan", "amplitude"))}
    return z, ignored


CC_RANGE_RE = re.compile(r"(lo|hi)cc(\d+)$")


def cc_open(region, control):
    """Whether a region sounds with every controller at its starting value (set_ccN in
    <control>, else 0), as sfizz plays a file with no CC input. Libraries gate variants on
    CCs - Big Cat Cello's voice count (cc107) selects among staccato and detuned multi-voice
    copies - and without this gate they were all mixed into one patch. A value that is not a
    number (a $define the parent program would supply) leaves the region open."""
    for k in region:
        m = CC_RANGE_RE.match(k)
        if not m:
            continue
        cc = int(m.group(2))
        try:
            val = float(control.get(f"set_cc{cc}", 0))
            lo = float(region.get(f"locc{cc}", 0))
            hi = float(region.get(f"hicc{cc}", 127))
        except ValueError:
            continue
        if not lo <= val <= hi:
            return False
    return True


def sample_base(sfz_path, regions, default_path="", root=None):
    """The folder sample paths resolve from. Normally the .sfz's own folder, but a sub-program
    (a mapping file a parent program #includes, e.g. Programs/mappings/ride_22/rd_brush_cl.sfz)
    writes its paths relative to that parent, because includes and samples resolve from the
    top-level file. Then the nearest ancestor folder (not above `root`) under which the most
    samples exist is used."""
    base = os.path.dirname(os.path.abspath(sfz_path))
    samples = [r["sample"].replace("\\", "/") for r in regions
               if "sample" in r and not r["sample"].startswith("*")][:24]
    if not samples:
        return base
    dp = default_path.replace("\\", "/")
    stop = os.path.normcase(os.path.abspath(root)) if root else None

    def hits(d):
        return sum(os.path.exists(os.path.normpath(os.path.join(d, dp, s))) for s in samples)

    best, best_hits, d = base, hits(base), base
    for _ in range(6):
        if best_hits == len(samples) or os.path.normcase(d) == stop:
            break
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
        h = hits(d)
        if h > best_hits:
            best, best_hits = d, h
    return best


def _zones(sfz_path, articulation=None, lib_root=None):
    """Sample zones for engine.Instrument.

    articulation: keyswitch note (int or name) to select; default = the file's sw_default,
    else the lowest keyswitch. Each zone: dict(path, root, lokey, hikey, lovel, hivel,
    tune_cents, keytrack, gain_db, layer).
    lib_root: the library folder; a sub-program's samples are looked for no higher than this.
    """
    regions, control = parse(sfz_path)
    default_path = control.get("default_path", "")
    base = sample_base(sfz_path, regions, default_path, lib_root)
    # a sub-program's CC starting values are set by its parent; if none of its sample regions
    # is open at 0, it was not meant to be read on its own with that gate, so keep them all
    gated = [r for r in regions if cc_open(r, control)]
    if any("sample" in r and r.get("trigger", "attack") == "attack" for r in gated):
        regions = gated
    switched = [r for r in regions if "sw_last" in r]
    if switched:
        want = articulation
        if want is None:
            dflt = [r["sw_default"] for r in regions if "sw_default" in r]
            want = dflt[0] if dflt else min(key_value(r["sw_last"]) for r in switched)
        want = key_value(str(want))
        regions = [r for r in regions if "sw_last" not in r or key_value(r["sw_last"]) == want]
    out = []
    for r in regions:
        if "sample" not in r or r.get("trigger", "attack") != "attack":
            continue
        if any(k.startswith(("on_locc", "on_hicc")) for k in r):   # pedal/hammer noises fired by CC
            continue
        sample = r["sample"].replace("\\", "/")
        if sample.startswith("*"):            # built-in oscillators (*sine, *noise...) - skip
            continue
        path = os.path.normpath(os.path.join(base, default_path.replace("\\", "/"), sample))
        if not os.path.exists(path):
            continue
        if "key" in r:
            lo = hi = key_value(r["key"])
            root = key_value(r.get("pitch_keycenter", r["key"]))
        else:
            lo = key_value(r.get("lokey", "0"))
            hi = key_value(r.get("hikey", "127"))
            root = key_value(r.get("pitch_keycenter", "60"))
        if hi < 0:
            continue
        tune = float(r.get("tune", 0)) + 100 * float(r.get("transpose", 0))
        # a region with no key at all is a sub-program's hit whose key the parent program
        # assigns (key=$rdrdkey): it plays at its recorded pitch on whatever note is used
        keyless = not any(k in r for k in ("key", "lokey", "hikey", "pitch_keycenter"))
        keytrack = float(r.get("pitch_keytrack", 0 if keyless else 100)) != 0
        out.append(dict(
            path=path, root=root, lokey=lo, hikey=hi,
            lovel=int(r.get("lovel", 1)), hivel=int(r.get("hivel", 127)),
            tune_cents=tune, keytrack=keytrack,
            gain_db=float(r.get("volume", 0)), layer=int(r.get("hivel", 127)),
        ))
    return out
