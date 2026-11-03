"""The command line answers and the fetch lock behaves."""
import subprocess
import sys
import threading
import time

from musicengine import fetch


def _run(*args):
    return subprocess.run([sys.executable, "-m", "musicengine", *args], capture_output=True, text=True)


def test_help_lists_new_commands():
    r = _run("--help")
    for cmd in ("reference", "compare", "loudness", "verify", "plan"):
        assert cmd in r.stdout


def test_plan_check_cli(tmp_path):
    from test_plan import EXAMPLE
    assert _run("plan", "check", str(EXAMPLE)).returncode == 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "nope"}')
    assert _run("plan", "check", str(bad)).returncode == 1


def test_fetch_lock_serializes(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "LIBRARY", tmp_path)
    order = []

    def worker(tag):
        with fetch._lock("lib"):
            order.append(tag + "-in")
            time.sleep(0.3)
            order.append(tag + "-out")

    ts = [threading.Thread(target=worker, args=(t,)) for t in "ab"]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert order[1].endswith("-out") and order[3].endswith("-out")
    assert not (tmp_path / "_tmp" / "lib.lock").exists()
