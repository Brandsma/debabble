"""Customisation: severity changes, rule edits, and the config cascade."""

from __future__ import annotations

import pytest

from debabble.config import Config, load_config, parse_config, resolve_ruleset
from debabble.errors import ConfigError
from debabble.models import Severity
from debabble.render import render_body


def parse(text: str) -> Config:
    import tomllib

    return parse_config(tomllib.loads(text))


# ---------------------------------------------------------------------------
# Severity: the quick knob
# ---------------------------------------------------------------------------


def test_severity_can_be_changed_for_one_rule():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [severity]
        "vocabulary.utilize" = "flag"
        """
    )
    rule = resolve_ruleset(config).rule("vocabulary.utilize")
    assert rule.severity is Severity.FLAG


def test_severity_can_be_changed_for_a_whole_pack():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [severity]
        vocabulary = "flag"
        """
    )
    ruleset = resolve_ruleset(config)
    assert all(r.severity is Severity.FLAG for r in ruleset.rules)


def test_a_rule_can_be_switched_off():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [severity]
        "vocabulary.utilize" = "off"
        """
    )
    ruleset = resolve_ruleset(config)
    assert ruleset.rule("vocabulary.utilize").severity is Severity.OFF
    assert "vocabulary.utilize" not in {r.id for r in ruleset.active_rules}


def test_a_rule_set_to_off_is_left_out_of_the_rendered_text():
    on = resolve_ruleset(parse('[profile]\npacks = ["chat-artifacts"]'))
    off = resolve_ruleset(
        parse(
            """
            [profile]
            packs = ["chat-artifacts"]
            [severity]
            chat-artifacts = "off"
            """
        )
    )
    assert "great question" in render_body(on).lower()
    assert "great question" not in render_body(off).lower()


def test_a_rule_specific_severity_beats_a_pack_wide_one():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [severity]
        vocabulary = "off"
        "vocabulary.utilize" = "ban"
        """
    )
    ruleset = resolve_ruleset(config)
    assert ruleset.rule("vocabulary.utilize").severity is Severity.BAN


def test_severity_from_the_command_line_wins_over_the_file():
    file_config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [severity]
        vocabulary = "off"
        """
    )
    merged = file_config.merged_with(Config(severity={"vocabulary": Severity.BAN}))
    assert all(r.severity is Severity.BAN for r in resolve_ruleset(merged).rules)


# ---------------------------------------------------------------------------
# Editing rules
# ---------------------------------------------------------------------------


def test_a_shipped_rule_can_be_edited_field_by_field():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]

        [[rules]]
        id = "vocabulary.utilize"
        instruction = "My own wording."
        words = ["utilize"]
        """
    )
    rule = resolve_ruleset(config).rule("vocabulary.utilize")
    assert rule.instruction == "My own wording."
    assert rule.words == ("utilize",)
    # Fields the override did not mention are kept.
    assert rule.severity is Severity.BAN


def test_a_brand_new_rule_can_be_defined():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]

        [[rules]]
        id = "no-shipping-metaphors"
        severity = "ban"
        kind = "phrase"
        phrases = ["ship it"]
        instruction = "Do not describe releases as shipping."
        """
    )
    ruleset = resolve_ruleset(config)
    rule = ruleset.rule("custom.no-shipping-metaphors")
    assert rule is not None
    assert rule.severity is Severity.BAN
    assert "Do not describe releases as shipping." in render_body(ruleset)


def test_editing_an_unknown_rule_in_a_known_pack_is_an_error():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]

        [[rules]]
        id = "vocabulary.does-not-exist"
        instruction = "x"
        """
    )
    with pytest.raises(ConfigError, match="No rule 'vocabulary.does-not-exist'"):
        resolve_ruleset(config)


# ---------------------------------------------------------------------------
# The one-line customisations
# ---------------------------------------------------------------------------


def test_avoid_adds_a_rule_of_your_own():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [custom]
        avoid = ["supercharge"]
        """
    )
    ruleset = resolve_ruleset(config)
    rule = ruleset.rule("custom.avoid")

    assert rule.words == ("supercharge",)
    assert rule.severity is Severity.BAN
    assert "supercharge" in render_body(ruleset)


def test_allow_removes_a_word_from_a_shipped_rule():
    without = resolve_ruleset(parse('[profile]\npacks = ["vocabulary"]'))
    with_allow = resolve_ruleset(
        parse(
            """
            [profile]
            packs = ["vocabulary"]
            [custom]
            allow = ["delve"]
            """
        )
    )
    assert "delve" in without.rule("vocabulary.hype-verbs").words
    assert "delve" not in with_allow.rule("vocabulary.hype-verbs").words
    # Only the exact word goes; its neighbours stay.
    assert "delving" in with_allow.rule("vocabulary.hype-verbs").words


def test_a_rule_emptied_by_allow_switches_itself_off():
    config = parse(
        """
        [profile]
        packs = ["vocabulary"]
        [custom]
        allow = ["utilize", "utilise"]
        """
    )
    assert resolve_ruleset(config).rule("vocabulary.utilize").severity is Severity.OFF


# ---------------------------------------------------------------------------
# Pack selection and the cascade
# ---------------------------------------------------------------------------


def test_default_packs_exclude_opt_in_packs():
    ruleset = resolve_ruleset(Config())
    ids = {p.id for p in ruleset.packs}
    assert "chat-artifacts" in ids
    assert "corporate-speak" not in ids


def test_an_opt_in_pack_can_be_asked_for():
    ruleset = resolve_ruleset(Config(packs=("corporate-speak",)))
    assert [p.id for p in ruleset.packs] == ["corporate-speak"]


def test_an_unknown_pack_lists_the_real_ones():
    with pytest.raises(ConfigError, match="Available packs"):
        resolve_ruleset(Config(packs=("nonsense",)))


def test_a_project_config_ignores_the_global_one(tmp_path, monkeypatch):
    """Committed output must be identical for everyone, whatever they set globally."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "debabble.toml").write_text(
        '[profile]\npacks = ["corporate-speak"]\n', encoding="utf-8"
    )
    monkeypatch.setattr("debabble.paths.user_config_dir", lambda: global_dir)

    project = tmp_path / "proj"
    project.mkdir()
    (project / "debabble.toml").write_text('[profile]\npacks = ["vocabulary"]\n', encoding="utf-8")

    config = load_config(project, scope="project")
    assert config.packs == ("vocabulary",)


def test_a_project_without_a_config_falls_back_to_the_global_one(tmp_path, monkeypatch):
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "debabble.toml").write_text(
        '[profile]\npacks = ["corporate-speak"]\n', encoding="utf-8"
    )
    monkeypatch.setattr("debabble.paths.user_config_dir", lambda: global_dir)

    project = tmp_path / "proj"
    project.mkdir()

    config = load_config(project, scope="project")
    assert config.packs == ("corporate-speak",)


def test_custom_packs_are_loaded_from_the_project(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    packs_dir = project / ".debabble" / "packs"
    packs_dir.mkdir(parents=True)
    (packs_dir / "house.toml").write_text(
        """
        [pack]
        id = "house"
        title = "House style"
        description = "Our own rules."

        [[rules]]
        id = "no-shipping"
        instruction = "Do not say ship."
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr("debabble.paths.global_packs_dir", lambda: tmp_path / "nowhere")

    ruleset = resolve_ruleset(Config(packs=("house",)), project_root=project)
    assert ruleset.rule("house.no-shipping") is not None


# ---------------------------------------------------------------------------
# Config errors name the problem
# ---------------------------------------------------------------------------


def test_an_unknown_section_is_rejected():
    with pytest.raises(ConfigError, match="unknown section"):
        parse("[nonsense]\nx = 1")


def test_an_unknown_profile_key_is_rejected():
    with pytest.raises(ConfigError, match="unknown key 'pack'"):
        parse("[profile]\npack = []")


def test_an_invalid_style_lists_the_valid_ones():
    with pytest.raises(ConfigError, match="compact"):
        parse('[profile]\nstyle = "fancy"')


def test_a_rule_without_an_id_is_rejected():
    with pytest.raises(ConfigError, match="needs an 'id'"):
        parse('[[rules]]\ninstruction = "x"')
