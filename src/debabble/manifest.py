"""A record of what debabble installed, so it can be checked and removed later.

The project manifest is meant to be committed. That is what lets a teammate who
clones the repository run ``debabble status`` and ``debabble remove`` and have
them work, even though backups only ever exist on the machine that wrote them.

For each installed file the manifest records whether debabble created it or only
added a block to it, which decides whether removal deletes the file or edits it.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import tomlkit

MANIFEST_VERSION = 1


def content_hash(text: str) -> str:
    """A stable hash of file content, insensitive to line-ending style."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class InstalledFile:
    """One file debabble wrote, and what it did to it."""

    target: str
    path: str
    strategy: str
    created: bool
    hash: str

    def resolve(self, root: Path | None) -> Path:
        path = Path(self.path)
        if path.is_absolute() or root is None:
            return path
        return root / path


@dataclass(frozen=True, slots=True)
class Manifest:
    """What a single scope has installed."""

    scope: str = "project"
    style: str = ""
    packs: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    files: tuple[InstalledFile, ...] = ()
    version: int = MANIFEST_VERSION

    @property
    def is_empty(self) -> bool:
        return not self.files

    def for_target(self, target_id: str) -> tuple[InstalledFile, ...]:
        return tuple(f for f in self.files if f.target == target_id)

    def installed_targets(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for f in self.files:
            seen.setdefault(f.target, None)
        return tuple(seen)

    def without_targets(self, target_ids: set[str]) -> Manifest:
        kept = tuple(f for f in self.files if f.target not in target_ids)
        return Manifest(
            scope=self.scope,
            style=self.style,
            packs=self.packs,
            targets=tuple(t for t in self.targets if t not in target_ids),
            files=kept,
            version=self.version,
        )


def load(path: Path, *, scope: str = "project") -> Manifest:
    """Read a manifest. A missing manifest means nothing is installed."""
    if not path.is_file():
        return Manifest(scope=scope)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        # A damaged manifest should not stop the tool from working; treat it as
        # empty and let the next apply write a fresh one.
        return Manifest(scope=scope)

    files = tuple(
        InstalledFile(
            target=str(entry.get("target", "")),
            path=str(entry.get("path", "")),
            strategy=str(entry.get("strategy", "own")),
            created=bool(entry.get("created", False)),
            hash=str(entry.get("hash", "")),
        )
        for entry in data.get("files", [])
        if isinstance(entry, dict)
    )
    return Manifest(
        scope=str(data.get("scope", scope)),
        style=str(data.get("style", "")),
        packs=tuple(str(p) for p in data.get("packs", [])),
        targets=tuple(str(t) for t in data.get("targets", [])),
        files=files,
        version=int(data.get("version", MANIFEST_VERSION)),
    )


def save(manifest: Manifest, path: Path) -> None:
    """Write a manifest, creating its directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {
        "version": manifest.version,
        "scope": manifest.scope,
        "style": manifest.style,
        "packs": list(manifest.packs),
        "targets": list(manifest.targets),
        "files": [asdict(f) for f in manifest.files],
    }
    header = (
        "# Written by debabble. Commit this file: it is what lets `debabble status`\n"
        "# and `debabble remove` work for anyone who clones this repository.\n\n"
    )
    path.write_text(header + tomlkit.dumps(document), encoding="utf-8")


def delete(path: Path) -> None:
    """Remove a manifest once nothing is installed any more."""
    if path.is_file():
        path.unlink()


__all__ = [
    "MANIFEST_VERSION",
    "InstalledFile",
    "Manifest",
    "content_hash",
    "delete",
    "load",
    "save",
]
