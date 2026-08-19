"""Where things live on disk, on every platform.

Windows, macOS, and Linux differ in three ways that matter here: the user
config directory, the home-relative tool directories, and the environment
variables tools honour. Every path debabble touches is resolved through this
module so those differences stay in one place.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "debabble"

# appauthor=False keeps Windows at %LOCALAPPDATA%\debabble rather than adding a
# vendor level, so the documented path matches what users actually see.
_dirs = PlatformDirs(appname=APP_NAME, appauthor=False)


def user_config_dir() -> Path:
    """Where the global debabble.toml and custom packs live."""
    return Path(_dirs.user_config_dir)


def user_data_dir() -> Path:
    """Where the global manifest and machine-local state live."""
    return Path(_dirs.user_data_dir)


def global_config_file() -> Path:
    return user_config_dir() / "debabble.toml"


def global_packs_dir() -> Path:
    return user_config_dir() / "packs"


def global_manifest_file() -> Path:
    return user_data_dir() / "manifest.toml"


def home() -> Path:
    return Path.home()


def env_dir(name: str) -> Path | None:
    """Read a directory from the environment, if it is set and non-empty."""
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def local_app_data() -> Path:
    """The Windows %LOCALAPPDATA% directory, with a sensible fallback elsewhere."""
    from_env = env_dir("LOCALAPPDATA")
    if from_env is not None:
        return from_env
    if os.name == "nt":
        return home() / "AppData" / "Local"
    return Path(_dirs.user_data_dir).parent


def find_project_root(start: Path | None = None) -> Path:
    """The nearest ancestor holding a marker of a project root.

    A ``.git`` directory wins; a ``debabble.toml`` or ``.debabble`` directory
    also counts, so the tool works in repositories that are not yet git
    repositories. Falls back to the starting directory.
    """
    current = (start or Path.cwd()).resolve()
    markers = (".git", "debabble.toml", ".debabble")
    for directory in (current, *current.parents):
        if any((directory / marker).exists() for marker in markers):
            return directory
    return current


def project_config_file(project_root: Path) -> Path:
    return project_root / "debabble.toml"


def project_state_dir(project_root: Path) -> Path:
    return project_root / ".debabble"


def project_packs_dir(project_root: Path) -> Path:
    return project_state_dir(project_root) / "packs"


def project_manifest_file(project_root: Path) -> Path:
    return project_state_dir(project_root) / "manifest.toml"


def project_backup_dir(project_root: Path) -> Path:
    """Backups are machine-local and gitignored; they never travel with a repo."""
    return project_state_dir(project_root) / "backups"


def display(path: Path, *, relative_to: Path | None = None) -> str:
    """Render a path for the terminal: relative when that is shorter and clearer."""
    try:
        if relative_to is not None:
            return str(path.resolve().relative_to(relative_to.resolve()))
    except ValueError:
        pass
    try:
        return "~/" + str(path.resolve().relative_to(home())).replace("\\", "/")
    except ValueError:
        return str(path)


__all__ = [
    "APP_NAME",
    "display",
    "env_dir",
    "find_project_root",
    "global_config_file",
    "global_manifest_file",
    "global_packs_dir",
    "home",
    "local_app_data",
    "project_backup_dir",
    "project_config_file",
    "project_manifest_file",
    "project_packs_dir",
    "project_state_dir",
    "user_config_dir",
    "user_data_dir",
]
