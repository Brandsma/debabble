"""Documentation must describe the tool that actually exists.

Rule ids, pack ids, and target ids get renamed during development, and prose
does not fail loudly when it goes stale. These tests make it fail loudly.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from debabble.cli import _STARTER_CONFIG
from debabble.config import STYLES, parse_config, resolve_ruleset
from debabble.models import Severity
from debabble.packs import load_all_packs
from debabble.targets import all_targets

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def known_pack_ids() -> set[str]:
    return {p.id for p in load_all_packs([])}


def known_rule_ids() -> set[str]:
    return {r.id for p in load_all_packs([]) for r in p.rules}


def test_starter_config_is_valid():
    """`debabble init` must write a file the tool can read back."""
    config = parse_config(tomllib.loads(_STARTER_CONFIG))
    resolve_ruleset(config)


def test_starter_config_names_real_packs_and_targets():
    config = parse_config(tomllib.loads(_STARTER_CONFIG))
    assert set(config.packs or ()) <= known_pack_ids()
    assert set(config.targets) <= {t.id for t in all_targets()}


def test_commented_examples_in_the_starter_config_are_real():
    """Even the commented-out lines should point at things that exist."""
    for rule_id in re.findall(r'#\s*id = "([\w.-]+)"', _STARTER_CONFIG):
        assert rule_id in known_rule_ids(), f"starter config mentions unknown rule {rule_id}"
    for quoted in re.findall(r'#\s*"([\w.-]+)" = "(?:ban|flag|off)"', _STARTER_CONFIG):
        assert quoted in known_rule_ids() | known_pack_ids(), (
            f"starter config mentions unknown rule or pack {quoted}"
        )


def test_readme_only_names_real_rules():
    mentioned = set(re.findall(r"\b((?:[a-z]+-)*[a-z]+\.[a-z][\w-]+)\b", README))
    # Keep only things that look like a rule id in a pack we ship.
    candidates = {m for m in mentioned if m.split(".", 1)[0] in known_pack_ids()}
    unknown = candidates - known_rule_ids()
    assert not unknown, f"README names rules that do not exist: {sorted(unknown)}"


def test_readme_target_table_matches_the_registry():
    """Every shipped target should be documented, and vice versa."""
    documented = set(re.findall(r"^\| `([\w-]+)` \|", README, re.MULTILINE))
    registered = {t.id for t in all_targets()}
    assert documented == registered, (
        f"missing from README: {sorted(registered - documented)}; "
        f"stale in README: {sorted(documented - registered)}"
    )


def test_readme_names_real_styles():
    for style in re.findall(r"`(minimal|compact|full|brief|terse)`", README):
        assert style in STYLES, f"README mentions unknown style {style}"


def test_readme_lists_the_default_packs_correctly():
    """The README claims which packs are on by default; that claim must hold."""
    defaults = {p.id for p in load_all_packs([]) if p.default}
    opt_in = {p.id for p in load_all_packs([]) if not p.default}

    claim = README.split("Packs on by default:", 1)[1].split("\n\n", 1)[0]
    claimed = set(re.findall(r"`([\w-]+)`", claim))

    assert claimed & defaults == defaults - {"custom"}, "README default pack list is stale"
    for pack_id in opt_in:
        assert f"`{pack_id}` is available but off" in README or pack_id in claim


def test_every_pack_cites_its_sources():
    """A rule pack makes claims about writing; it should say where they come from."""
    for pack in load_all_packs([]):
        if pack.id == "minimal-docs":
            continue  # editorial judgement rather than measured tells
        assert pack.references, f"{pack.id} cites no references"


def test_every_ban_rule_explains_itself():
    """A ban is the strongest thing debabble says, so it must be legible."""
    for pack in load_all_packs([]):
        for rule in pack.rules:
            if rule.severity is Severity.BAN:
                assert rule.instruction.strip(), rule.id
                assert rule.title, f"{rule.id} has no title to show in rendered output"
