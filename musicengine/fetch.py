"""Download library content on demand into the central library, pinned and license-checked.

git libraries: a partial, sparse clone of exactly the requested paths at the pinned commit,
moved into LIBRARY/<library id>/ and recorded per path in .fetched.json, so a library can
grow one folder at a time and a re-fetch months later gets the same files.
file libraries: one download checked against its sha256.
Before anything is marked usable, license/readme files that came with it are scanned; a
ShareAlike / NonCommercial / Sampling Plus grant stops the fetch.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from .config import LIBRARY, FORBIDDEN_LICENSE_PATTERNS

LICENSE_NAMES = ("license", "licence", "copying", "readme")


class LicenseProblem(RuntimeError):
    pass


def _marker(lib_id):
    return LIBRARY / lib_id / ".fetched.json"


def fetched(lib_id):
    p = _marker(lib_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_marker(lib_id, data):
    p = _marker(lib_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _rmtree(p):
    """rmtree that also removes git's read-only pack files on Windows."""
    import os
    import stat

    def onerror(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if Path(p).exists():
        shutil.rmtree(p, onerror=onerror)


def _git(*args, cwd=None):
    r = subprocess.run(["git", "-c", "core.longpaths=true", *args], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def scan_licenses(root, allow=()):
    """Raise LicenseProblem if a license/readme file under root grants a forbidden license.
    allow: relative paths a human already reviewed (catalog `license_reviewed`)."""
    hits = []
    for f in Path(root).rglob("*"):
        if not f.is_file() or not f.name.lower().startswith(LICENSE_NAMES):
            continue
        rel = f.relative_to(root).as_posix()
        if rel in allow:
            continue
        text = f.read_text(encoding="utf-8", errors="replace").lower()
        for pat in FORBIDDEN_LICENSE_PATTERNS:
            m = re.search(pat, text)
            if m:
                i = m.start()
                hits.append(f"{rel}: ...{text[max(0, i - 80): i + 60]!r}...")
                break
    if hits:
        raise LicenseProblem("license files mention a forbidden license:\n  " + "\n  ".join(hits))


def ensure_git(lib, paths):
    """lib: catalog library dict (id, git, commit, license_reviewed?). paths: repo-relative
    folders ('' = whole repo). Fetches only what is missing; returns the library dir."""
    lib_id = lib["id"]
    dest = LIBRARY / lib_id
    have = fetched(lib_id)
    if not [p for p in paths if p not in have and "" not in have]:
        return dest
    with _lock(lib_id):              # parallel renders may want the same library
        have = fetched(lib_id)
        missing = [p for p in paths if p not in have and "" not in have]
        if not missing:
            return dest
        tmp = LIBRARY / "_tmp" / f"{lib_id}-{os.getpid()}"
        _rmtree(tmp)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        print(f"[fetch] {lib_id}: {', '.join(p or '<all>' for p in missing)}")
        try:
            _fetch_into(lib, missing, tmp, dest, have)
        finally:
            _rmtree(tmp)
    return dest


@contextlib.contextmanager
def _lock(lib_id, wait_s=1800):
    """A cross-process lock file per library. A lock older than wait_s is a crashed fetch."""
    path = LIBRARY / "_tmp" / f"{lib_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > wait_s:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() - t0 > wait_s:
                raise TimeoutError(f"{path} held for {wait_s} s; delete it if no fetch is running")
            time.sleep(1.0)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _fetch_into(lib, missing, tmp, dest, have):
    lib_id = lib["id"]
    _git("clone", "--quiet", "--filter=blob:none", "--no-checkout", lib["git"], str(tmp))
    if "" not in missing:
        # root docs come along so their license text is scanned - unless the library's own
        # license evidence lives in the fetched folder (e.g. Sonic Pi: MIT code, CC0 samples)
        pats = ["/*.md", "/*.txt", "/LICENSE*", "/license*", "/COPYING*"] if lib.get("root_docs", True) else []
        pats += ["/" + p.strip("/") + "/" for p in missing]
        _git("sparse-checkout", "set", "--no-cone", *pats, cwd=tmp)
    _git("checkout", "--quiet", lib["commit"], cwd=tmp)
    scan_licenses(tmp, allow=set(lib.get("license_reviewed", [])))
    for p in missing:
        src = tmp / p if p else tmp
        if not src.exists():
            raise FileNotFoundError(f"{lib_id}: path {p!r} does not exist at {lib['commit'][:10]}")
    dest.mkdir(parents=True, exist_ok=True)
    if "" in missing:
        for item in tmp.iterdir():
            if item.name != ".git":
                target = dest / item.name
                if target.exists():
                    shutil.rmtree(target) if target.is_dir() else target.unlink()
                shutil.move(str(item), str(target))
    else:
        for p in missing + [f.name for f in tmp.iterdir() if f.is_file()]:
            src, target = tmp / p, dest / p
            if not src.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(src), str(target))
    today = datetime.date.today().isoformat()
    for p in missing:
        have[p] = dict(commit=lib["commit"], date=today)
    _save_marker(lib_id, have)


def ensure_file(lib):
    """lib: dict(id, url, sha256, filename). Downloads once, verifies the hash."""
    dest = LIBRARY / lib["id"] / lib["filename"]
    if dest.exists():
        return dest
    with _lock(lib["id"]):
        if dest.exists():
            return dest
        return _download_file(lib, dest)


def _download_file(lib, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"[fetch] {lib['id']}: {lib['url']}")
    h = hashlib.sha256()
    with urllib.request.urlopen(lib["url"]) as r, open(part, "wb") as fh:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            fh.write(chunk)
    if lib.get("sha256") and h.hexdigest() != lib["sha256"]:
        part.unlink()
        raise RuntimeError(f"{lib['id']}: sha256 mismatch ({h.hexdigest()})")
    if lib.get("license_url"):
        lic = dest.parent / "LICENSE.md"
        urllib.request.urlretrieve(lib["license_url"], lic)
        scan_licenses(dest.parent)
    part.rename(dest)
    _save_marker(lib["id"], {lib["filename"]: dict(sha256=h.hexdigest(), date=datetime.date.today().isoformat())})
    return dest
