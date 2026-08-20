"""Installing, checking, and removing the rules.

Everything that touches a user's files goes through here, and every operation
can be previewed with ``dry_run=True`` before anything is written.

Two promises shape this module. Re-running ``apply`` with unchanged settings
changes nothing on disk. And ``remove`` puts things back: files debabble created
are deleted, files it only added a block to are edited back, and a backup taken
before the first modification is restored when one exists.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import managed_block, paths
from . import manifest as manifest_mod
from .config import Config
from .manifest import InstalledFile, Manifest, content_hash
from .models import RuleSet
from .render import render, render_rewrite_command
from .targets import CONTENT_REWRITE, Target, TargetFile, format_frontmatter, get_target

# Rough allowance for the markers and note wrapped around a managed block.
_BLOCK_OVERHEAD = 160

CREATE = "create"
UPDATE = "update"
UNCHANGED = "unchanged"
DELETE = "delete"
STRIP = "strip"
RESTORE = "restore"
SKIP = "skip"
MISSING = "missing"
DRIFT = "drift"


@dataclass(frozen=True, slots=True)
class Change:
    """One thing that happened, or would happen, to one file."""

    target: str
    path: Path
    action: str
    detail: str = ""

    @property
    def is_write(self) -> bool:
        return self.action in (CREATE, UPDATE, DELETE, STRIP, RESTORE)


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result of an operation, including what it would have done."""

    changes: tuple[Change, ...] = ()
    warnings: tuple[str, ...] = ()
    manifest: Manifest | None = None
    dry_run: bool = False

    @property
    def wrote_anything(self) -> bool:
        return any(c.is_write for c in self.changes)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def manifest_path(scope: str, project_root: Path | None) -> Path:
    if scope == "global" or project_root is None:
        return paths.global_manifest_file()
    return paths.project_manifest_file(project_root)


def backup_dir(scope: str, project_root: Path | None) -> Path:
    if scope == "global" or project_root is None:
        return paths.user_data_dir() / "backups"
    return paths.project_backup_dir(project_root)


def _backup_name(path: Path) -> str:
    """A filesystem-safe name that still hints at where the file came from."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(path)).strip("-")
    return f"{stem[-80:]}.{content_hash(str(path))[:8]}.bak"


def _record_path(path: Path, scope: str, project_root: Path | None) -> str:
    """Store project paths relative so a manifest survives being cloned elsewhere."""
    if scope == "project" and project_root is not None:
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def build_content(
    target_file: TargetFile, ruleset: RuleSet, style: str
) -> tuple[str, tuple[str, ...]]:
    """Render what should go in one file, and any warnings about fitting it."""
    header = format_frontmatter(target_file.frontmatter) if target_file.owns_file else ""

    if target_file.content == CONTENT_REWRITE:
        return header + render_rewrite_command(ruleset, style=style), ()

    budget = target_file.budget
    if budget is not None:
        budget -= len(header)
        if not target_file.owns_file:
            budget -= _BLOCK_OVERHEAD

    result = render(ruleset, style=style, budget=budget)
    warnings: list[str] = []
    if result.dropped_examples:
        warnings.append("examples were dropped to fit the size limit")
    if result.dropped_packs:
        warnings.append(f"packs dropped to fit the size limit: {', '.join(result.dropped_packs)}")
    if budget is not None and len(result.text) > budget:
        warnings.append(
            f"content is {len(result.text)} characters but the limit is {target_file.budget}; "
            "reduce the enabled packs or use --style compact"
        )
    return header + result.text, tuple(warnings)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _ensure_backup(path: Path, scope: str, project_root: Path | None, *, dry_run: bool) -> None:
    """Snapshot a pre-existing file once, before debabble first modifies it."""
    directory = backup_dir(scope, project_root)
    destination = directory / _backup_name(path)
    if destination.exists() or not path.is_file():
        return
    if dry_run:
        return
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def _restore_backup(path: Path, scope: str, project_root: Path | None, *, dry_run: bool) -> bool:
    source = backup_dir(scope, project_root) / _backup_name(path)
    if not source.is_file():
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
        source.unlink()
    return True


def ensure_backups_ignored(project_root: Path) -> None:
    """Keep machine-local backups out of git, without disturbing the rest of .gitignore."""
    if not (project_root / ".git").exists():
        return
    gitignore = project_root / ".gitignore"
    entry = ".debabble/backups/"
    existing = _read(gitignore) or ""
    if entry in existing:
        return
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    addition = f"{prefix}\n# debabble keeps machine-local backups here\n{entry}\n"
    gitignore.write_text(existing + addition, encoding="utf-8")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def apply(
    ruleset: RuleSet,
    config: Config,
    *,
    scope: str = "project",
    project_root: Path | None = None,
    target_ids: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> Outcome:
    """Write the rules into every selected target.

    ``target_ids`` of None means "whatever the configuration asks for", and in
    that case targets that were installed before but are no longer configured
    are removed. Naming targets explicitly refreshes only those and prunes
    nothing, so a one-off ``--target`` cannot quietly uninstall anything.
    """
    style = config.effective_style
    wanted = tuple(target_ids) if target_ids is not None else config.effective_targets
    explicit = target_ids is not None

    path_of_manifest = manifest_path(scope, project_root)
    previous = manifest_mod.load(path_of_manifest, scope=scope)

    changes: list[Change] = []
    warnings: list[str] = []
    installed: list[InstalledFile] = []

    for target_id in wanted:
        target = get_target(target_id)
        files = target.files(scope, project_root)
        if not files:
            note = target.note(scope) or f"{target.title} has no {scope} rules file."
            changes.append(Change(target_id, Path(), SKIP, note))
            continue
        if target.note(scope):
            warnings.append(f"{target_id}: {target.note(scope)}")

        for target_file in files:
            change, record = _apply_one(
                target=target,
                target_file=target_file,
                ruleset=ruleset,
                style=style,
                scope=scope,
                project_root=project_root,
                dry_run=dry_run,
                warnings=warnings,
            )
            changes.append(change)
            if record is not None:
                installed.append(record)

    # Carry forward records for targets this run did not touch.
    touched = {r.target for r in installed} | {c.target for c in changes if c.action == SKIP}
    kept = [f for f in previous.files if f.target not in touched]

    if explicit:
        installed.extend(kept)
    else:
        stale = {f.target for f in kept}
        for target_id in sorted(stale):
            removal = _remove_target(
                target_id,
                tuple(f for f in kept if f.target == target_id),
                scope=scope,
                project_root=project_root,
                dry_run=dry_run,
            )
            changes.extend(removal)
            warnings.append(f"{target_id}: removed, because it is no longer in your targets")

    new_manifest = Manifest(
        scope=scope,
        style=style,
        packs=tuple(p.id for p in ruleset.packs),
        targets=tuple(dict.fromkeys(r.target for r in installed)),
        files=tuple(installed),
    )

    if not dry_run:
        if new_manifest.is_empty:
            manifest_mod.delete(path_of_manifest)
        else:
            manifest_mod.save(new_manifest, path_of_manifest)
        if scope == "project" and project_root is not None and any(c.is_write for c in changes):
            ensure_backups_ignored(project_root)

    return Outcome(
        changes=tuple(changes),
        warnings=tuple(dict.fromkeys(warnings)),
        manifest=new_manifest,
        dry_run=dry_run,
    )


def _apply_one(
    *,
    target: Target,
    target_file: TargetFile,
    ruleset: RuleSet,
    style: str,
    scope: str,
    project_root: Path | None,
    dry_run: bool,
    warnings: list[str],
) -> tuple[Change, InstalledFile | None]:
    body, fit_warnings = build_content(target_file, ruleset, style)
    for warning in fit_warnings:
        warnings.append(f"{target.id}: {warning}")

    path = target_file.path
    existing = _read(path)
    created = existing is None

    if target_file.owns_file:
        new_text = body if body.endswith("\n") else body + "\n"
    else:
        new_text = managed_block.upsert(existing or "", body)

    if existing is not None and existing == new_text:
        action = UNCHANGED
    else:
        action = CREATE if created else UPDATE
        if not created:
            _ensure_backup(path, scope, project_root, dry_run=dry_run)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_text, encoding="utf-8")

    record = InstalledFile(
        target=target.id,
        path=_record_path(path, scope, project_root),
        strategy=target_file.strategy,
        created=created,
        hash=content_hash(new_text),
    )
    detail = "" if action != UNCHANGED else "already up to date"
    return Change(target.id, path, action, detail), record


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def remove(
    *,
    scope: str = "project",
    project_root: Path | None = None,
    target_ids: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> Outcome:
    """Uninstall, using the manifest to know exactly what debabble put there."""
    path_of_manifest = manifest_path(scope, project_root)
    current = manifest_mod.load(path_of_manifest, scope=scope)

    if current.is_empty:
        return Outcome(warnings=("Nothing is installed in this scope.",), dry_run=dry_run)

    wanted = set(target_ids) if target_ids else set(current.installed_targets())
    unknown = wanted - set(current.installed_targets())
    warnings = [f"{t}: not installed here, nothing to remove" for t in sorted(unknown)]

    changes: list[Change] = []
    for target_id in sorted(wanted & set(current.installed_targets())):
        changes.extend(
            _remove_target(
                target_id,
                current.for_target(target_id),
                scope=scope,
                project_root=project_root,
                dry_run=dry_run,
            )
        )

    remaining = current.without_targets(wanted)
    if not dry_run:
        if remaining.is_empty:
            manifest_mod.delete(path_of_manifest)
        else:
            manifest_mod.save(remaining, path_of_manifest)

    return Outcome(
        changes=tuple(changes),
        warnings=tuple(warnings),
        manifest=remaining,
        dry_run=dry_run,
    )


def _remove_target(
    target_id: str,
    records: tuple[InstalledFile, ...],
    *,
    scope: str,
    project_root: Path | None,
    dry_run: bool,
) -> list[Change]:
    root = project_root if scope == "project" else None
    changes: list[Change] = []

    for record in records:
        path = record.resolve(root)
        existing = _read(path)

        if existing is None:
            changes.append(Change(target_id, path, MISSING, "already gone"))
            continue

        if record.created:
            if not dry_run:
                path.unlink()
            changes.append(Change(target_id, path, DELETE))
            continue

        if _restore_backup(path, scope, project_root, dry_run=dry_run):
            changes.append(Change(target_id, path, RESTORE, "restored from backup"))
            continue

        stripped = managed_block.remove(existing)
        if stripped == existing:
            changes.append(Change(target_id, path, MISSING, "no debabble block found"))
            continue
        if not dry_run:
            if stripped.strip():
                path.write_text(stripped, encoding="utf-8")
            else:
                path.unlink()
        changes.append(Change(target_id, path, STRIP, "removed the debabble block"))

    return changes


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StatusEntry:
    target: str
    path: Path
    state: str
    detail: str = ""


def status(
    ruleset: RuleSet,
    config: Config,
    *,
    scope: str = "project",
    project_root: Path | None = None,
) -> tuple[Manifest, tuple[StatusEntry, ...]]:
    """Report what is installed, whether it is current, and whether it was edited."""
    path_of_manifest = manifest_path(scope, project_root)
    current = manifest_mod.load(path_of_manifest, scope=scope)
    root = project_root if scope == "project" else None
    style = config.effective_style

    entries: list[StatusEntry] = []
    for record in current.files:
        path = record.resolve(root)
        existing = _read(path)
        if existing is None:
            entries.append(StatusEntry(record.target, path, MISSING, "file is gone"))
            continue

        if content_hash(existing) != record.hash:
            entries.append(
                StatusEntry(record.target, path, DRIFT, "edited since debabble wrote it")
            )
            continue

        target = get_target(record.target)
        matching = [f for f in target.files(scope, project_root or Path.cwd()) if f.path == path]
        if matching:
            body, _ = build_content(matching[0], ruleset, style)
            expected = (
                (body if body.endswith("\n") else body + "\n")
                if matching[0].owns_file
                else managed_block.upsert(existing, body)
            )
            state = UNCHANGED if expected == existing else UPDATE
            detail = "" if state == UNCHANGED else "settings changed; run apply"
            entries.append(StatusEntry(record.target, path, state, detail))
        else:
            entries.append(StatusEntry(record.target, path, UNCHANGED))

    return current, tuple(entries)


def lint_excludes(
    config: Config, *, scope: str = "project", project_root: Path | None = None
) -> tuple[str, ...]:
    """Paths ``debabble lint`` should skip: configured ones, plus our own output.

    The files debabble writes contain the rules themselves, word lists and all.
    Checking them would report every banned term as a violation of itself.
    """
    installed = manifest_mod.load(manifest_path(scope, project_root), scope=scope)
    return config.exclude + tuple(f.path for f in installed.files)


def shadowing_warnings(project_root: Path | None) -> tuple[str, ...]:
    """Files that make another tool ignore what debabble wrote to AGENTS.md."""
    if project_root is None:
        return ()
    found: list[str] = []
    for name, tool in (
        (".rules", "Zed"),
        (".cursorrules", "Zed"),
        ("AGENTS.override.md", "Codex"),
    ):
        if (project_root / name).exists():
            found.append(
                f"{tool} reads {name} before AGENTS.md, so it will not see the block there."
            )
    return tuple(dict.fromkeys(found))


__all__ = [
    "CREATE",
    "DELETE",
    "DRIFT",
    "MISSING",
    "RESTORE",
    "SKIP",
    "STRIP",
    "UNCHANGED",
    "UPDATE",
    "Change",
    "Outcome",
    "StatusEntry",
    "apply",
    "backup_dir",
    "build_content",
    "ensure_backups_ignored",
    "manifest_path",
    "remove",
    "shadowing_warnings",
    "status",
]
