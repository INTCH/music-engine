"""The README's code runs, and the docs that plans and AGENTS.md point at exist."""
import json
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _python_blocks(path):
    return re.findall(r"```python\n(.*?)```", path.read_text(encoding="utf-8"), flags=re.S)


def _block(marker):
    blocks = [b for b in _python_blocks(ROOT / "README.md") if marker in b]
    assert len(blocks) == 1, marker
    return blocks[0]


def _run(code, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "snippet.py"
    script.write_text(code, encoding="utf-8")
    runpy.run_path(str(script), run_name="__main__")


def test_readme_synth_example_runs(tmp_path, monkeypatch):
    _run(_block("allow_synth=True"), tmp_path, monkeypatch)
    side = json.loads((tmp_path / "out" / "house.render.json").read_text(encoding="utf-8"))
    assert side["licenses"] == ["Synthesized"]


@pytest.mark.samples
def test_readme_quickstart_runs(tmp_path, monkeypatch):
    _run(_block('"violins"'), tmp_path, monkeypatch)
    side = json.loads((tmp_path / "out" / "track.render.json").read_text(encoding="utf-8"))
    assert side["recorded_only"] is True
    assert (tmp_path / "out" / "track.mid").exists()


def test_plan_sources_point_at_docs_in_the_repo():
    for plan in (ROOT / "examples" / "plans").glob("*.plan.json"):
        for r in json.loads(plan.read_text(encoding="utf-8"))["rationale"]:
            if r.get("source"):
                path, _, anchor = r["source"].split(" ")[0].partition("#")
                doc = ROOT / path
                assert doc.exists(), r["source"]
                if anchor:
                    heads = {re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-")
                             for h in re.findall(r"^#+ (.+)$", doc.read_text(encoding="utf-8"), flags=re.M)}
                    assert anchor in heads, r["source"]


def test_markdown_links_resolve():
    for md in [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CLAUDE.md", *(ROOT / "docs").rglob("*.md")]:
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", md.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("../../releases"):
                continue
            assert (md.parent / target).exists(), f"{md.name}: {target}"


def test_no_owner_specific_paths_in_docs():
    for md in [ROOT / "README.md", ROOT / "AGENTS.md", *(ROOT / "docs").rglob("*.md")]:
        text = md.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\Users|/home/\w+|Desktop", text), md.name
