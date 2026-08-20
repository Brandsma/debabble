"""Installing and removing must never damage what someone else wrote.

These tests exercise the two promises the install engine makes: applying twice
changes nothing the second time, and removing puts the file back the way it was.
"""

from __future__ import annotations

import pytest

from debabble import install, managed_block
from debabble import manifest as manifest_mod
from debabble.config import Config, resolve_ruleset

USER_TEXT = """# Team notes

Always run the migration before deploying.
"""


@pytest.fixture
def ruleset():
    return resolve_ruleset(Config(packs=("chat-artifacts",)))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project directory with debabble's global state redirected into it."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.setattr("debabble.paths.user_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr("debabble.paths.user_config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr("debabble.paths.home", lambda: tmp_path / "home")
    return root


def _apply(ruleset, project, targets, **kwargs):
    return install.apply(
        ruleset,
        Config(targets=targets),
        scope="project",
        project_root=project,
        target_ids=None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Owned files
# ---------------------------------------------------------------------------


def test_apply_creates_an_owned_file(ruleset, project):
    outcome = _apply(ruleset, project, ("claude-code",))
    path = project / ".claude" / "rules" / "debabble.md"

    assert path.is_file()
    assert "Writing rules" in path.read_text(encoding="utf-8")
    assert [c.action for c in outcome.changes] == [install.CREATE]


def test_applying_twice_changes_nothing(ruleset, project):
    _apply(ruleset, project, ("claude-code",))
    path = project / ".claude" / "rules" / "debabble.md"
    first = path.read_text(encoding="utf-8")

    outcome = _apply(ruleset, project, ("claude-code",))

    assert path.read_text(encoding="utf-8") == first
    assert [c.action for c in outcome.changes] == [install.UNCHANGED]


def test_remove_deletes_a_file_debabble_created(ruleset, project):
    _apply(ruleset, project, ("claude-code",))
    path = project / ".claude" / "rules" / "debabble.md"

    install.remove(scope="project", project_root=project)

    assert not path.exists()


def test_frontmatter_is_written_for_targets_that_need_it(ruleset, project):
    _apply(ruleset, project, ("cursor",))
    text = (project / ".cursor" / "rules" / "debabble.mdc").read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "alwaysApply: true" in text


# ---------------------------------------------------------------------------
# Managed blocks in files the user owns
# ---------------------------------------------------------------------------


def test_block_target_keeps_existing_content(ruleset, project):
    agents = project / "AGENTS.md"
    agents.write_text(USER_TEXT, encoding="utf-8")

    _apply(ruleset, project, ("agents-md",))
    text = agents.read_text(encoding="utf-8")

    assert "Always run the migration before deploying." in text
    assert managed_block.BEGIN in text
    assert "Writing rules" in text


def test_reapplying_replaces_only_the_block(ruleset, project):
    agents = project / "AGENTS.md"
    agents.write_text(USER_TEXT, encoding="utf-8")
    _apply(ruleset, project, ("agents-md",))

    # Someone adds a note after debabble's block.
    agents.write_text(agents.read_text(encoding="utf-8") + "\nOne more note.\n", encoding="utf-8")

    _apply(ruleset, project, ("agents-md",))
    text = agents.read_text(encoding="utf-8")

    assert "Always run the migration before deploying." in text
    assert "One more note." in text
    assert text.count(managed_block.BEGIN) == 1


def test_remove_restores_the_original_file(ruleset, project):
    agents = project / "AGENTS.md"
    agents.write_text(USER_TEXT, encoding="utf-8")

    _apply(ruleset, project, ("agents-md",))
    install.remove(scope="project", project_root=project)

    assert agents.read_text(encoding="utf-8") == USER_TEXT


def test_remove_works_without_a_backup(ruleset, project):
    """A fresh clone has the manifest but no backups; removal must still be clean."""
    agents = project / "AGENTS.md"
    agents.write_text(USER_TEXT, encoding="utf-8")
    _apply(ruleset, project, ("agents-md",))

    for leftover in install.backup_dir("project", project).glob("*.bak"):
        leftover.unlink()

    install.remove(scope="project", project_root=project)
    text = agents.read_text(encoding="utf-8")

    assert managed_block.BEGIN not in text
    assert "Always run the migration before deploying." in text


def test_block_target_creates_the_file_when_absent(ruleset, project):
    _apply(ruleset, project, ("agents-md",))
    agents = project / "AGENTS.md"
    assert agents.is_file()

    install.remove(scope="project", project_root=project)
    assert not agents.exists()


def test_crlf_files_keep_their_line_endings(ruleset, project):
    agents = project / "AGENTS.md"
    agents.write_bytes(USER_TEXT.replace("\n", "\r\n").encode("utf-8"))

    _apply(ruleset, project, ("agents-md",))
    raw = agents.read_bytes()

    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_hermes_uses_its_own_context_file(ruleset, project):
    _apply(ruleset, project, ("hermes",))
    path = project / ".hermes.md"

    assert path.is_file()
    assert managed_block.BEGIN in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dry run, manifest, pruning, status
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(ruleset, project):
    outcome = _apply(ruleset, project, ("claude-code",), dry_run=True)

    assert outcome.dry_run
    assert [c.action for c in outcome.changes] == [install.CREATE]
    assert not (project / ".claude").exists()
    assert not install.manifest_path("project", project).exists()


def test_manifest_records_what_was_written(ruleset, project):
    _apply(ruleset, project, ("claude-code", "agents-md"))
    loaded = manifest_mod.load(install.manifest_path("project", project))

    assert set(loaded.installed_targets()) == {"claude-code", "agents-md"}
    # Project paths are stored relative so a clone elsewhere still resolves them.
    assert all(not entry.path.startswith(str(project)) for entry in loaded.files)


def test_dropping_a_target_from_config_uninstalls_it(ruleset, project):
    _apply(ruleset, project, ("claude-code", "agents-md"))
    assert (project / "AGENTS.md").exists()

    _apply(ruleset, project, ("claude-code",))

    assert not (project / "AGENTS.md").exists()
    assert (project / ".claude" / "rules" / "debabble.md").exists()


def test_naming_targets_explicitly_prunes_nothing(ruleset, project):
    _apply(ruleset, project, ("claude-code", "agents-md"))

    install.apply(
        ruleset,
        Config(targets=("claude-code", "agents-md")),
        scope="project",
        project_root=project,
        target_ids=("claude-code",),
    )

    assert (project / "AGENTS.md").exists()


def test_status_notices_a_hand_edited_file(ruleset, project):
    _apply(ruleset, project, ("claude-code",))
    path = project / ".claude" / "rules" / "debabble.md"
    path.write_text("someone rewrote this\n", encoding="utf-8")

    _, entries = install.status(
        ruleset, Config(targets=("claude-code",)), scope="project", project_root=project
    )

    assert [e.state for e in entries] == [install.DRIFT]


def test_status_notices_out_of_date_content(ruleset, project):
    _apply(ruleset, project, ("claude-code",))
    bigger = resolve_ruleset(Config(packs=("chat-artifacts", "vocabulary")))

    _, entries = install.status(
        bigger, Config(targets=("claude-code",)), scope="project", project_root=project
    )

    assert [e.state for e in entries] == [install.UPDATE]


def test_backups_are_gitignored(ruleset, project):
    agents = project / "AGENTS.md"
    agents.write_text(USER_TEXT, encoding="utf-8")

    _apply(ruleset, project, ("agents-md",))

    assert ".debabble/backups/" in (project / ".gitignore").read_text(encoding="utf-8")


def test_a_target_without_a_scope_is_skipped_not_failed(ruleset, project):
    outcome = install.apply(
        ruleset,
        Config(targets=("cursor",)),
        scope="global",
        project_root=None,
    )

    assert [c.action for c in outcome.changes] == [install.SKIP]
    assert "application settings" in outcome.changes[0].detail


# ---------------------------------------------------------------------------
# Global scope
# ---------------------------------------------------------------------------


def test_a_global_install_round_trips(ruleset, project, tmp_path):
    """Installing user-wide writes outside any project, and removes cleanly."""
    home = tmp_path / "home"
    home.mkdir()

    outcome = install.apply(
        ruleset,
        Config(targets=("claude-code", "gemini")),
        scope="global",
        project_root=None,
    )
    written = [c.path for c in outcome.changes if c.action == install.CREATE]

    assert written, "nothing was written globally"
    assert all(project not in p.parents for p in written), "a global install wrote into a project"
    assert all(p.is_file() for p in written)

    install.remove(scope="global", project_root=None)
    assert not any(p.exists() for p in written)


def test_hermes_global_uses_its_own_home(ruleset, project, tmp_path, monkeypatch):
    """Hermes has no global rules file, so its block goes in SOUL.md."""
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    install.apply(ruleset, Config(targets=("hermes",)), scope="global", project_root=None)
    soul = hermes_home / "SOUL.md"

    assert soul.is_file()
    assert managed_block.BEGIN in soul.read_text(encoding="utf-8")

    install.remove(scope="global", project_root=None)
    assert not soul.exists()
