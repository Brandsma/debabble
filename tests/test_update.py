"""`debabble update` has to pick the upgrade command the machine actually needs.

The wrong command is worse than no command: pip installing over a uv tool venv
leaves two copies of debabble and the one on PATH is whichever the shell finds
first. Detection reads the directory layout, so these tests build each layout
in a tmp_path and check what comes back.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from debabble import update
from debabble.errors import UpdateError


@pytest.fixture
def on_path(monkeypatch):
    """Pretend every package manager is installed, wherever the test runs."""
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/opt/bin/{name}")


def make_venv(root, *marker_files: str):
    """A virtualenv holding debabble, and the package directory inside it."""
    package = root / "lib" / "python3.12" / "site-packages" / "debabble"
    package.mkdir(parents=True)
    (root / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    for name in marker_files:
        (root / name).write_text("", encoding="utf-8")
    return package


def test_a_uv_tool_install_upgrades_with_uv(tmp_path, on_path):
    package = make_venv(tmp_path / "tools" / "debabble", "uv-receipt.toml")
    found = update.detect(package)
    assert found.kind == update.UV_TOOL
    assert update.shell_command(found) == "uv tool upgrade debabble"


def test_a_uv_tool_install_is_recognised_without_a_receipt(tmp_path, on_path):
    """Older uv versions wrote no receipt, and those installs still update."""
    package = make_venv(tmp_path / "uv" / "tools" / "debabble")
    assert update.detect(package).kind == update.UV_TOOL


def test_a_pipx_install_upgrades_with_pipx(tmp_path, on_path):
    package = make_venv(tmp_path / "venvs" / "debabble", "pipx_metadata.json")
    found = update.detect(package)
    assert found.kind == update.PIPX
    assert update.shell_command(found) == "pipx upgrade debabble"


def test_a_plain_virtualenv_upgrades_with_pip(tmp_path, on_path):
    package = make_venv(tmp_path / "env")
    found = update.detect(package)
    assert found.kind == update.PIP
    assert found.command[:2] == (sys.executable, "-m")
    assert found.command[-1] == "debabble"


def test_a_checkout_is_left_to_git(tmp_path, on_path):
    checkout = tmp_path / "debabble"
    package = checkout / "src" / "debabble"
    package.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    found = update.detect(package)
    assert found.kind == update.SOURCE
    assert found.command == ()
    assert "git pull" in found.reason


def test_a_manager_that_left_the_path_gets_a_command_to_type(tmp_path, monkeypatch):
    monkeypatch.setattr(update.shutil, "which", lambda name: None)
    package = make_venv(tmp_path / "tools" / "debabble", "uv-receipt.toml")

    found = update.detect(package)
    assert found.kind == update.UV_TOOL
    assert found.command == ()
    assert "uv tool upgrade debabble" in found.reason


def test_the_printed_command_drops_the_directory(tmp_path, on_path):
    package = make_venv(tmp_path / "tools" / "debabble", "uv-receipt.toml")
    assert "/opt/bin" not in update.shell_command(update.detect(package))


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("0.3.0", "0.2.0", True),
        ("0.10.0", "0.9.0", True),  # string comparison gets this one wrong
        ("0.2.0", "0.2.0", False),
        ("0.2", "0.2.0", False),
        ("1.0.0", "0.99.99", True),
        ("0.2.0", "0.0.0+unknown", True),  # running from an uninstalled checkout
        ("0.3.0rc1", "0.2.0", True),
    ],
)
def test_version_comparison(candidate, current, newer):
    assert update.is_newer(candidate, current) is newer


def test_a_failed_upgrade_says_which_command_failed(tmp_path, on_path, monkeypatch):
    monkeypatch.setattr(
        update.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, returncode=2)
    )
    installation = update.detect(make_venv(tmp_path / "tools" / "debabble", "uv-receipt.toml"))
    with pytest.raises(UpdateError, match="uv tool upgrade debabble exited 2"):
        update.run_upgrade(installation)


def test_an_upgrade_with_nothing_to_run_raises_its_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(update.shutil, "which", lambda name: None)
    installation = update.detect(make_venv(tmp_path / "tools" / "debabble", "uv-receipt.toml"))
    with pytest.raises(UpdateError, match="not on your PATH"):
        update.run_upgrade(installation)


def test_the_latest_release_comes_from_pypi(monkeypatch):
    payload = json.dumps({"info": {"version": "9.9.9"}}).encode("utf-8")
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload))
    assert update.latest_release() == "9.9.9"


def test_an_unreachable_pypi_is_an_error_not_a_traceback(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(update.urllib.request, "urlopen", refuse)
    with pytest.raises(UpdateError, match="Could not ask PyPI"):
        update.latest_release()
