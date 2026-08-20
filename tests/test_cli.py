"""The command line, run the way a user runs it.

These go through the real entry point in a subprocess. They are slower than the
library tests, so they cover the journeys the README promises rather than every
branch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow


def run(*args: str, cwd, expect_ok: bool = True) -> subprocess.CompletedProcess:
    """Run debabble in a directory and return the finished process."""
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        # Keep the test off the developer's real global configuration.
        "XDG_CONFIG_HOME": str(cwd / "_xdg_config"),
        "XDG_DATA_HOME": str(cwd / "_xdg_data"),
        "LOCALAPPDATA": str(cwd / "_appdata"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "debabble.cli", *args],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(
            f"debabble {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "README.md").write_text("# Project\n\nDoes a thing.\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# The journeys in the README
# ---------------------------------------------------------------------------


def test_init_then_apply_then_remove(project):
    run("init", cwd=project)
    assert (project / "debabble.toml").is_file()

    run("apply", cwd=project)
    installed = project / ".claude" / "rules" / "debabble.md"
    assert installed.is_file()
    assert "Writing rules" in installed.read_text(encoding="utf-8")

    run("remove", cwd=project)
    assert not installed.exists()


def test_apply_works_without_any_config(project):
    """A fresh directory should just work."""
    run("apply", cwd=project)
    assert (project / ".claude" / "rules" / "debabble.md").is_file()


def test_dry_run_writes_nothing(project):
    result = run("apply", "--dry-run", cwd=project)
    assert "created" in result.stdout
    assert not (project / ".claude").exists()


def test_status_reports_what_is_installed(project):
    run("apply", cwd=project)
    result = run("status", cwd=project)

    assert "claude-code" in result.stdout
    assert "unchanged" in result.stdout


def test_bare_invocation_is_useful(project):
    result = run(cwd=project)
    assert "rules active" in result.stdout


# ---------------------------------------------------------------------------
# Customisation from the command line
# ---------------------------------------------------------------------------


def test_avoid_adds_a_word_and_it_reaches_the_output(project):
    run("init", cwd=project)
    run("avoid", "supercharge", cwd=project)
    run("apply", cwd=project)

    text = (project / ".claude" / "rules" / "debabble.md").read_text(encoding="utf-8")
    assert "supercharge" in text


def test_severity_changes_persist(project):
    run("init", cwd=project)
    run("severity", "vocabulary.hype-verbs", "flag", cwd=project)

    config = (project / "debabble.toml").read_text(encoding="utf-8")
    assert "vocabulary.hype-verbs" in config
    assert "flag" in config


def test_severity_works_for_a_pack_that_is_switched_off(project):
    """corporate-speak ships disabled; setting its severity must still work."""
    run("init", cwd=project)
    run("severity", "corporate-speak", "ban", cwd=project)
    assert "corporate-speak" in (project / "debabble.toml").read_text(encoding="utf-8")


def test_save_keeps_a_target_that_a_later_apply_would_prune(project):
    run("init", cwd=project)
    run("apply", "--target", "agents-md", "--save", cwd=project)
    assert (project / "AGENTS.md").is_file()

    # A plain apply reconciles against the config; the saved target survives.
    run("apply", cwd=project)
    assert (project / "AGENTS.md").is_file()


def test_an_unsaved_target_is_flagged_as_temporary(project):
    run("init", cwd=project)
    result = run("apply", "--target", "agents-md", cwd=project)
    assert "--save" in result.stdout


def test_saving_a_target_does_not_drop_the_others(project):
    run("init", cwd=project)
    run("apply", "--target", "agents-md", "--save", cwd=project)

    config = (project / "debabble.toml").read_text(encoding="utf-8")
    assert "claude-code" in config
    assert "agents-md" in config


# ---------------------------------------------------------------------------
# Reading the rules
# ---------------------------------------------------------------------------


def test_rules_prints_pasteable_toml(project):
    result = run("rules", "vocabulary.hype-verbs", cwd=project)
    assert "[[rules]]" in result.stdout
    assert "vocabulary.hype-verbs" in result.stdout


def test_a_rule_pasted_back_into_the_config_takes_effect(project):
    """The README promises this round trip."""
    run("init", cwd=project)
    (project / "debabble.toml").write_text(
        (project / "debabble.toml").read_text(encoding="utf-8")
        + '\n[[rules]]\nid = "vocabulary.hype-verbs"\nseverity = "flag"\n'
        + 'instruction = "My own wording for this."\n'
        + 'words = ["delve"]\n',
        encoding="utf-8",
    )
    run("apply", cwd=project)

    text = (project / ".claude" / "rules" / "debabble.md").read_text(encoding="utf-8")
    assert "My own wording for this." in text


def test_packs_and_targets_list_something(project):
    assert "chat-artifacts" in run("packs", cwd=project).stdout
    assert "hermes" in run("targets", cwd=project).stdout


def test_render_writes_to_stdout_only(project):
    result = run("render", "--style", "minimal", cwd=project)
    assert result.stdout.startswith("# Writing rules")
    assert not (project / ".claude").exists()


# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------


def test_lint_fails_on_banned_writing(project):
    (project / "bad.md").write_text("Great question! I hope this helps.\n", encoding="utf-8")
    result = run("lint", "bad.md", cwd=project, expect_ok=False)

    assert result.returncode == 1
    assert "sycophancy" in result.stdout


def test_lint_passes_on_ordinary_writing(project):
    (project / "ok.md").write_text("The cache expires after 300 seconds.\n", encoding="utf-8")
    result = run("lint", "ok.md", cwd=project)

    assert result.returncode == 0
    assert "No findings" in result.stdout


def test_lint_json_is_machine_readable(project):
    (project / "bad.md").write_text("Great question!\n", encoding="utf-8")
    result = run("lint", "bad.md", "--format", "json", cwd=project, expect_ok=False)

    payload = json.loads(result.stdout)
    assert payload[0]["rule"] == "chat-artifacts.sycophancy"
    assert payload[0]["line"] == 1


def test_lint_does_not_flag_the_files_debabble_wrote(project):
    """Generated rule files contain every banned word by definition."""
    run("apply", cwd=project)
    result = run("lint", ".", cwd=project)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Errors are actionable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("apply", "--pack", "nonsense"), "Available packs"),
        (("apply", "--target", "nonsense"), "Available targets"),
        (("apply", "--severity", "broken"), "ID=LEVEL"),
        (("severity", "nonsense", "ban"), "debabble packs"),
        (("apply", "--style", "fancy"), "minimal"),
    ],
)
def test_errors_say_what_to_do(project, args, expected):
    result = run(*args, cwd=project, expect_ok=False)
    assert result.returncode != 0
    assert expected in (result.stdout + result.stderr)


def test_a_broken_config_names_the_file(project):
    (project / "debabble.toml").write_text("[profile]\npacks = 3\n", encoding="utf-8")
    result = run("status", cwd=project, expect_ok=False)

    assert "debabble.toml" in (result.stdout + result.stderr)


def test_a_typo_in_a_rule_field_is_explained(project):
    (project / "debabble.toml").write_text(
        '[[rules]]\nid = "mine.x"\ninstruction = "Do a thing."\nsevrity = "ban"\n',
        encoding="utf-8",
    )
    result = run("status", cwd=project, expect_ok=False)

    assert "severity" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# Messages that have to survive being printed
# ---------------------------------------------------------------------------


def test_a_config_error_still_names_the_section(project):
    """Rich reads [profile] as markup; the message must escape it."""
    (project / "debabble.toml").write_text("[nonsense]\nx = 1\n", encoding="utf-8")
    result = run("status", cwd=project, expect_ok=False)

    assert "[nonsense]" in (result.stdout + result.stderr)


def test_linting_a_path_that_is_not_there_is_an_error(project):
    result = run("lint", "no-such-file.md", cwd=project, expect_ok=False)

    assert result.returncode != 0
    assert "No such file" in (result.stdout + result.stderr)


def test_forcing_a_register_still_walks_directories(project):
    (project / "docs").mkdir()
    (project / "docs" / "a.md").write_text("Great question!\n", encoding="utf-8")

    result = run("lint", "docs", "--register", "docs", cwd=project, expect_ok=False)

    assert result.returncode == 1
    assert "sycophancy" in result.stdout


def test_a_typo_in_a_severity_id_is_refused(project):
    result = run("apply", "--severity", "vocabulari=off", "--dry-run", cwd=project, expect_ok=False)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "vocabulary" in output, "the error should suggest the real id"


def test_a_mistyped_command_suggests_the_real_one(project):
    result = run("aply", cwd=project, expect_ok=False)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "apply" in output


def test_severity_on_a_pack_that_is_off_says_it_has_no_effect(project):
    run("init", cwd=project)
    result = run("severity", "corporate-speak", "ban", cwd=project)

    assert "no effect" in result.stdout
