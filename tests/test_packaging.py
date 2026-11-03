"""Packaging and external tools: the catalog ships inside the package, the engine version works
without git, and external renderer binaries are found or verified before they run."""
import io
import zipfile
from importlib.metadata import version

import pytest

from musicengine import config, external, score


def test_catalog_ships_inside_the_package():
    assert config.CATALOG_DIR.parent == config.PACKAGE
    assert (config.CATALOG_DIR / "aliases.toml").exists()
    assert list((config.CATALOG_DIR / "generated").glob("*.toml"))


def test_engine_version_falls_back_to_the_package_version(tmp_path, monkeypatch):
    monkeypatch.setattr(score, "REPO", tmp_path)            # no .git there
    assert score.engine_version() == version("musicengine")


def test_tool_from_environment_variable(tmp_path, monkeypatch):
    exe = tmp_path / "my_sfizz_render"
    exe.write_bytes(b"")
    monkeypatch.setenv("MUSICENGINE_SFIZZ_RENDER", str(exe))
    assert external.tool("sfizz_render") == exe
    monkeypatch.setenv("MUSICENGINE_SFIZZ_RENDER", str(tmp_path / "missing"))
    with pytest.raises(external.ToolMissing):
        external.tool("sfizz_render")


def test_missing_tool_off_windows_gives_install_hints(monkeypatch):
    monkeypatch.delenv("MUSICENGINE_FLUIDSYNTH", raising=False)
    monkeypatch.setattr(external.shutil, "which", lambda name: None)
    monkeypatch.setattr(external, "_IS_WINDOWS", False)
    monkeypatch.setattr(external, "_download", lambda name: pytest.fail("must not download off Windows"))
    with pytest.raises(external.ToolMissing, match="install FluidSynth"):
        external.tool("fluidsynth")


def test_download_with_a_wrong_hash_is_not_extracted(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bin/sfizz_render.exe", b"not the real thing")
    monkeypatch.setattr(external, "TOOLS", tmp_path)
    monkeypatch.setattr(external.urllib.request, "urlretrieve", lambda url, path: open(path, "wb").write(buf.getvalue()))
    with pytest.raises(external.ToolMissing, match="SHA-256"):
        external._download("sfizz_render")
    assert not list(tmp_path.rglob("sfizz_render.exe"))


def test_download_with_the_right_hash_is_extracted(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bin/sfizz_render.exe", b"stand-in")
    data = buf.getvalue()
    import hashlib
    spec = dict(external.TOOL_ZIPS["sfizz_render"], sha256=hashlib.sha256(data).hexdigest())
    monkeypatch.setitem(external.TOOL_ZIPS, "sfizz_render", spec)
    monkeypatch.setattr(external, "TOOLS", tmp_path)
    monkeypatch.setattr(external.urllib.request, "urlretrieve", lambda url, path: open(path, "wb").write(data))
    exe = external._download("sfizz_render")
    assert exe.read_bytes() == b"stand-in"
    monkeypatch.setattr(external.urllib.request, "urlretrieve", lambda *a: pytest.fail("already verified"))
    assert external._download("sfizz_render") == exe
