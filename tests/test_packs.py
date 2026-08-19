"""Every shipped pack must load, and the loader must reject bad input clearly."""

from __future__ import annotations

import re

import pytest

from debabble.errors import PackError
from debabble.models import CHANNELS, KINDS, REGISTERS, Severity
from debabble.packs import build_pack, builtin_pack_files, load_builtin_packs, load_pack_file

MINIMAL = {
    "pack": {"id": "demo", "title": "Demo", "description": "d"},
    "rules": [{"id": "one", "instruction": "Write plainly."}],
}


def test_every_builtin_pack_loads():
    packs = load_builtin_packs()
    assert packs, "no packs were found in the package data directory"
    for pack in packs:
        assert pack.id
        assert pack.description, f"{pack.id} has no description"
        assert pack.rules, f"{pack.id} has no rules"


def test_rule_ids_are_unique_across_packs():
    seen: dict[str, str] = {}
    for pack in load_builtin_packs():
        for rule in pack.rules:
            assert rule.id not in seen, f"{rule.id} is defined in both {seen.get(rule.id)} and {pack.id}"
            seen[rule.id] = pack.id


def test_rules_are_internally_consistent():
    for pack in load_builtin_packs():
        for rule in pack.rules:
            assert rule.kind in KINDS
            assert rule.instruction.strip(), f"{rule.id} has an empty instruction"
            assert set(rule.registers) <= set(REGISTERS), rule.id
            assert set(rule.channels) <= set(CHANNELS), rule.id
            assert rule.channels, f"{rule.id} is delivered nowhere"
            if rule.kind == "wordlist":
                assert rule.words, rule.id
            if rule.kind == "phrase":
                assert rule.phrases, rule.id
            if rule.kind == "regex":
                assert rule.pattern, rule.id


def test_every_regex_compiles():
    for pack in load_builtin_packs():
        for rule in pack.rules:
            if rule.pattern:
                re.compile(rule.pattern)


def test_no_regex_matches_the_empty_string():
    """A pattern that matches nothing at all would flag every line of every file."""
    for pack in load_builtin_packs():
        for rule in pack.rules:
            if rule.pattern:
                assert not re.search(rule.pattern, ""), f"{rule.id} matches the empty string"


def test_pack_files_contain_no_invisible_characters():
    """Private-use and zero-width characters slip in from pasted model output."""
    bad = re.compile("[\ue000-\uf8ff\u200b-\u200f\u2060\ufeff]")
    for path in builtin_pack_files():
        text = path.read_text(encoding="utf-8")
        assert not bad.search(text), f"{path.name} contains an invisible character"


def test_severity_parsing_accepts_synonyms():
    assert Severity.parse("ban") is Severity.BAN
    assert Severity.parse("WARN") is Severity.FLAG
    assert Severity.parse("none") is Severity.OFF


def test_severity_parsing_rejects_nonsense():
    with pytest.raises(PackError, match="not a severity"):
        Severity.parse("maybe")


def test_unknown_rule_field_is_reported_with_a_suggestion():
    data = {**MINIMAL, "rules": [{"id": "one", "instruction": "x", "sevrity": "ban"}]}
    with pytest.raises(PackError, match="Did you mean 'severity'"):
        build_pack(data, source="test")


def test_rule_without_instruction_is_rejected():
    data = {**MINIMAL, "rules": [{"id": "one"}]}
    with pytest.raises(PackError, match="needs an 'instruction'"):
        build_pack(data, source="test")


def test_wordlist_without_words_is_rejected():
    data = {**MINIMAL, "rules": [{"id": "one", "instruction": "x", "kind": "wordlist"}]}
    with pytest.raises(PackError, match="lists no 'words'"):
        build_pack(data, source="test")


def test_short_ids_are_qualified_with_the_pack():
    pack = build_pack(MINIMAL, source="test")
    assert pack.rules[0].id == "demo.one"
    assert pack.rules[0].pack == "demo"
    assert pack.rules[0].short_id == "one"


def test_duplicate_rule_ids_are_rejected():
    data = {
        **MINIMAL,
        "rules": [{"id": "one", "instruction": "a"}, {"id": "one", "instruction": "b"}],
    }
    with pytest.raises(PackError, match="duplicate rule id"):
        build_pack(data, source="test")


def test_a_broken_pack_file_names_itself(tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("this is not toml = = =", encoding="utf-8")
    with pytest.raises(PackError, match="not valid TOML"):
        load_pack_file(path)
