"""Updating debabble itself.

debabble is installed four ways: `uv tool install`, `pipx install`, plain pip,
and a git checkout. Each wants a different upgrade command, and running the
wrong one either fails or installs a second copy that shadows the first. This
module works out which install is running from where the package sits on disk,
so `debabble update` runs the command that matches it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .errors import UpdateError

PYPI_URL = "https://pypi.org/pypi/debabble/json"

UV_TOOL = "uv tool"
PIPX = "pipx"
PIP = "pip"
SOURCE = "source checkout"


@dataclass(frozen=True, slots=True)
class Installation:
    """How this copy of debabble got here, and how to upgrade it.

    ``command`` is empty when debabble cannot do the upgrade itself, and then
    ``reason`` says what the reader should run instead.
    """

    kind: str
    root: Path
    command: tuple[str, ...] = ()
    reason: str = ""


def detect(package_dir: Path | None = None) -> Installation:
    """Work out how the running debabble was installed.

    ``package_dir`` is the directory holding this module. Tests pass a
    synthetic one so every install layout can be checked on any machine.
    """
    here = (package_dir or Path(__file__).resolve().parent).resolve()
    root = _environment_root(here)

    if (root / "uv-receipt.toml").is_file() or _sits_under(root, "uv", "tools"):
        return _managed(UV_TOOL, root, "uv", ("tool", "upgrade", "debabble"))
    if (root / "pipx_metadata.json").is_file() or _sits_under(root, "pipx", "venvs"):
        return _managed(PIPX, root, "pipx", ("upgrade", "debabble"))
    if (root / "pyproject.toml").is_file():
        return Installation(
            kind=SOURCE,
            root=root,
            reason=f"debabble runs from the checkout at {root}, so git pull updates it.",
        )
    return Installation(
        kind=PIP,
        root=root,
        command=(sys.executable, "-m", "pip", "install", "--upgrade", "debabble"),
    )


def shell_command(installation: Installation) -> str:
    """The upgrade command written the way someone would type it."""
    if not installation.command:
        return ""
    # which() returns an absolute path, and that path is noise in a message
    # about a command the reader could run themselves.
    program, *arguments = installation.command
    return " ".join([Path(program).name, *arguments])


def run_upgrade(installation: Installation) -> None:
    """Run the upgrade, leaving the package manager's own output on screen."""
    if not installation.command:
        raise UpdateError(installation.reason)
    try:
        completed = subprocess.run(installation.command, check=False)
    except OSError as err:
        raise UpdateError(f"Could not run {shell_command(installation)}: {err}") from err
    if completed.returncode != 0:
        raise UpdateError(
            f"{shell_command(installation)} exited {completed.returncode}. "
            "The output above is from the package manager."
        )


def latest_release(*, timeout: float = 10.0) -> str:
    """Ask PyPI for the newest published version of debabble."""
    request = urllib.request.Request(
        PYPI_URL,
        headers={"Accept": "application/json", "User-Agent": f"debabble/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        return str(payload["info"]["version"])
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise UpdateError(f"Could not ask PyPI for the latest version: {err}") from err


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a later release than ``current``."""
    left, right = _release(candidate), _release(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _release(version: str) -> tuple[int, ...]:
    """The leading numbers of a version.

    packaging is not a dependency and debabble ships plain x.y.z versions, so
    comparing the numbers is enough. Anything after them, such as an rc suffix
    or a local version, is dropped.
    """
    match = re.match(r"\d+(?:\.\d+)*", version.strip())
    if match is None:
        return (0,)
    return tuple(int(part) for part in match.group().split("."))


def _environment_root(package_dir: Path) -> Path:
    """The virtualenv or checkout the package lives in.

    A virtualenv is marked by pyvenv.cfg. An editable install points back at a
    checkout, which has no pyvenv.cfg above it, so pyproject.toml counts too.
    """
    for parent in package_dir.parents:
        if (parent / "pyvenv.cfg").is_file() or (parent / "pyproject.toml").is_file():
            return parent
    return package_dir.parent


def _sits_under(root: Path, *parts: str) -> bool:
    """Whether these directory names appear in order in the path.

    A fallback for installs whose marker file a package manager has not always
    written, such as uv tool venvs from before uv-receipt.toml existed.
    """
    names = root.parts
    return any(names[i : i + len(parts)] == parts for i in range(len(names)))


def _managed(kind: str, root: Path, program: str, arguments: tuple[str, ...]) -> Installation:
    """An install owned by a package manager, if that manager is still on PATH."""
    found = shutil.which(program)
    typed = " ".join([program, *arguments])
    if found is None:
        return Installation(
            kind=kind,
            root=root,
            reason=f"{program} installed debabble but is not on your PATH now. Run: {typed}",
        )
    return Installation(kind=kind, root=root, command=(found, *arguments))
