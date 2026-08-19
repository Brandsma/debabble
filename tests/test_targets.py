"""Targets must resolve sane paths on Windows, macOS, and Linux.

Path handling is the part of debabble most likely to break on a platform the
author is not using, so these tests check the invariants rather than exact
strings: project files stay inside the project, global files stay inside the
user's home or app data, and every target is reachable in at least one scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debabble.errors import TargetError
from debabble.targets import all_targets, format_frontmatter, get_target


@pytest.fixture
def root(tmp_path):
    return tmp_path / "project"


def test_every_target_is_available_in_at_least_one_scope(root):
    for target in all_targets():
        reachable = target.files("project", root) or target.files("global", None)
        assert reachable, f"{target.id} writes nothing in any scope"


def test_project_files_stay_inside_the_project(root):
    for target in all_targets():
        for target_file in target.files("project", root):
            assert root in target_file.path.parents or target_file.path.parent == root, (
                f"{target.id} writes outside the project: {target_file.path}"
            )


def test_global_files_are_outside_any_project(root):
    for target in all_targets():
        for target_file in target.files("global", None):
            assert root not in target_file.path.parents


def test_a_target_with_no_scope_explains_itself():
    """A target that cannot serve a scope owes the user a reason."""
    for target in all_targets():
        for scope in ("project", "global"):
            files = target.files(scope, Path("/tmp/x") if scope == "project" else None)
            if not files:
                assert target.note(scope), f"{target.id} silently does nothing in {scope} scope"


def test_unknown_target_lists_the_real_ones():
    with pytest.raises(TargetError, match="Available targets"):
        get_target("nonsense")


def test_unknown_scope_is_rejected(root):
    with pytest.raises(TargetError, match="Use 'project' or 'global'"):
        get_target("claude-code").files("sideways", root)


def test_owned_files_and_blocks_are_distinguished(root):
    claude = get_target("claude-code").files("project", root)[0]
    agents = get_target("agents-md").files("project", root)[0]

    assert claude.owns_file
    assert not agents.owns_file


def test_windsurf_prefers_the_devin_directory_when_it_exists(root):
    root.mkdir(parents=True)
    before = get_target("windsurf").files("project", root)[0].path
    assert ".windsurf" in before.parts

    (root / ".devin").mkdir()
    after = get_target("windsurf").files("project", root)[0].path
    assert ".devin" in after.parts


def test_hermes_honours_its_home_variable(root, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "custom-hermes"))
    path = get_target("hermes").files("global", None)[0].path

    assert path.parent == tmp_path / "custom-hermes"
    assert path.name == "SOUL.md"


def test_hermes_project_file_is_its_own_context_file(root):
    path = get_target("hermes").files("project", root)[0].path
    assert path == root / ".hermes.md"


def test_size_limited_targets_declare_a_budget(root):
    windsurf_project = get_target("windsurf").files("project", root)[0]
    windsurf_global = get_target("windsurf").files("global", None)[0]

    # Windsurf documents 12,000 characters per workspace rule file and 6,000
    # for the global one; exceeding either is silently truncated by the tool.
    assert windsurf_project.budget == 12000
    assert windsurf_global.budget == 6000


def test_frontmatter_keeps_the_order_the_target_declared():
    rendered = format_frontmatter((("description", "x"), ("alwaysApply", "true")))
    assert rendered.splitlines()[:4] == ["---", "description: x", "alwaysApply: true", "---"]


def test_no_frontmatter_renders_as_nothing():
    assert format_frontmatter(()) == ""


def test_target_ids_are_unique():
    ids = [t.id for t in all_targets()]
    assert len(ids) == len(set(ids))
