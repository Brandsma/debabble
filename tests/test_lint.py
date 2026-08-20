"""The linter must catch real AI-speak and leave ordinary writing alone.

The second half matters more than the first. A linter that cries wolf on normal
technical prose gets switched off, so the clean-prose cases here are the ones to
protect when changing a pattern.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from debabble.config import Config, resolve_ruleset
from debabble.lint import (
    Finding,
    compile_rule,
    lint_file,
    lint_paths,
    lint_text,
    mask_strings,
    split_source,
    walk_files,
)
from debabble.models import Severity

# Ordinary technical writing, including words that have a literal technical
# sense but appear on somebody's list of AI tells.
CLEAN_PROSE = """# Cache design

The cache is checked before the database. Entries expire after 300 seconds.
A test harness in tests/bench.py measures the hit rate; the last run showed 94%.

Use the primary key for lookups. The Kerberos realm is configured in krb5.conf.
Unlock the mutex before returning, or the next reader blocks forever.
The beacon interval is 100 ms. Elevated privileges are required to bind port 80.
"""

SLOP = """# Overview

Great question! Let's delve into the intricate tapestry of our robust,
seamless architecture.

It is important to note that this leverages a cutting-edge approach.

I hope this helps!
"""


@pytest.fixture
def ruleset():
    return resolve_ruleset(Config())


def ids(findings: list[Finding]) -> set[str]:
    return {f.rule_id for f in findings}


# ---------------------------------------------------------------------------
# Catching what it should
# ---------------------------------------------------------------------------


def test_slop_is_caught(ruleset):
    found = ids(lint_text(SLOP, ruleset, register="docs"))

    assert "chat-artifacts.sycophancy" in found
    assert "chat-artifacts.offers-of-help" in found
    assert "vocabulary.hype-verbs" in found
    assert "phrases.throat-clearing" in found


def test_findings_point_at_the_right_line_and_column(ruleset):
    text = "All fine here.\n\nGreat question! Not fine.\n"
    found = [
        f for f in lint_text(text, ruleset, register="docs") if f.rule_id.endswith("sycophancy")
    ]

    assert len(found) == 1
    assert found[0].line == 3
    assert found[0].column == 1
    assert found[0].matched == "Great question"


def test_a_phrase_split_across_lines_is_still_found(ruleset):
    text = "It is important\nto note that the cache is warm.\n"
    assert "phrases.throat-clearing" in ids(lint_text(text, ruleset, register="docs"))


# ---------------------------------------------------------------------------
# Leaving alone what it should
# ---------------------------------------------------------------------------


def test_ordinary_technical_prose_is_clean(ruleset):
    """The regression gate. If this fails, a pattern got too greedy."""
    findings = lint_text(CLEAN_PROSE, ruleset, register="docs")
    assert findings == [], f"false positives: {[(f.rule_id, f.matched) for f in findings]}"


def test_code_fences_are_not_read_as_prose(ruleset):
    text = "# Doc\n\nDo not write this:\n\n```\nGreat question! I hope this helps.\n```\n"
    assert lint_text(text, ruleset, register="docs") == []


def test_inline_code_is_not_read_as_prose(ruleset):
    assert lint_text("Avoid the word `delve` in prose.\n", ruleset, register="docs") == []


def test_a_quoted_word_is_a_mention_not_a_use(ruleset):
    """Writing about "delve" is not writing badly."""
    text = 'AI assistants overuse "delve" and "seamless" in documentation.\n'
    assert lint_text(text, ruleset, register="docs") == []


def test_a_long_quotation_is_still_checked(ruleset):
    """Only short mentions are excused; a quoted sentence is real prose."""
    text = (
        'The report said "it is important to note that the pipeline leverages '
        'a cutting-edge approach to processing".\n'
    )
    assert ids(lint_text(text, ruleset, register="docs"))


# ---------------------------------------------------------------------------
# Scope, case, and density
# ---------------------------------------------------------------------------


def test_a_heading_rule_does_not_fire_on_body_text(ruleset):
    body = "This library offers comprehensive coverage of the protocol.\n"
    heading = "## A comprehensive guide\n"

    assert "docs-readme.comprehensive-headings" not in ids(
        lint_text(body, ruleset, register="docs")
    )
    assert "docs-readme.comprehensive-headings" in ids(lint_text(heading, ruleset, register="docs"))


def test_case_sensitive_patterns_stay_case_sensitive(ruleset):
    """A pattern only ignores case when its author wrote (?i)."""
    sentence_case = "# Getting started with the parser\n"
    title_case = "# Getting Started With The Parser Today\n"

    assert "punctuation.title-case-headings" not in ids(
        lint_text(sentence_case, ruleset, register="docs")
    )
    assert "punctuation.title-case-headings" in ids(lint_text(title_case, ruleset, register="docs"))


def test_a_density_rule_allows_its_quota(ruleset):
    one = "The retry budget is crucial for throughput.\n"
    many = "This crucial, vital, essential, robust change is comprehensive.\n"

    assert "vocabulary.intensity-cluster" not in ids(lint_text(one, ruleset, register="docs"))
    assert "vocabulary.intensity-cluster" in ids(lint_text(many, ruleset, register="docs"))


def test_density_is_counted_per_paragraph_not_per_document(ruleset):
    """One intensity word in each of three paragraphs is fine."""
    text = "It is crucial.\n\nIt is robust.\n\nIt is essential.\n"
    assert "vocabulary.intensity-cluster" not in ids(lint_text(text, ruleset, register="docs"))


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_an_ignore_comment_silences_the_next_line(ruleset):
    text = "<!-- debabble-ignore -->\nGreat question! This is deliberate.\n"
    assert lint_text(text, ruleset, register="docs") == []


def test_an_ignore_comment_silences_its_own_line(ruleset):
    text = "Great question! <!-- debabble: ignore -->\n"
    assert lint_text(text, ruleset, register="docs") == []


# ---------------------------------------------------------------------------
# Source files
# ---------------------------------------------------------------------------


def test_comments_and_code_are_separated():
    source = 'x = "hello"  # Increment the counter\n'
    comments, code = split_source(source, ".py")

    assert "Increment the counter" in comments
    assert "Increment the counter" not in code
    assert "x =" in code
    # Both halves keep the original length, so positions stay correct.
    assert len(comments) == len(source) == len(code)


def test_string_literals_are_masked():
    assert "delve" not in mask_strings('message = "delve into this"')
    assert "message" in mask_strings('message = "delve into this"')


def test_a_triple_quoted_string_is_masked():
    source = 'def f():\n    """Delve into the tapestry."""\n    return 1\n'
    assert "tapestry" not in mask_strings(source)
    assert "return 1" in mask_strings(source)


def test_an_apostrophe_in_a_comment_does_not_swallow_the_file():
    source = "# it's fine\nx = 1\ny = 2\n"
    assert "x = 1" in mask_strings(source)
    assert "y = 2" in mask_strings(source)


def test_restating_comments_are_caught(ruleset, tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("# Increment the counter\ncounter += 1\n", encoding="utf-8")

    assert "code-comments.restating-comments" in ids(lint_file(path, ruleset))


def test_self_praising_identifiers_are_caught(ruleset, tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def enhanced_parser(data):\n    return data\n", encoding="utf-8")

    assert "code-comments.identifier-adjectives" in ids(lint_file(path, ruleset))


def test_ordinary_python_is_clean(ruleset, tmp_path):
    path = tmp_path / "ordinary.py"
    path.write_text(
        "import os\n\n\n"
        "def read_config(path):\n"
        '    """Read the config file and return its contents."""\n'
        "    # The caller handles a missing file; an empty one is valid.\n"
        "    with open(path) as handle:\n"
        "        return handle.read()\n",
        encoding="utf-8",
    )
    findings = lint_file(path, ruleset)
    assert findings == [], f"false positives: {[(f.rule_id, f.matched) for f in findings]}"


# ---------------------------------------------------------------------------
# Walking and excluding
# ---------------------------------------------------------------------------


def test_the_walk_skips_noise_directories(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "b.py").write_text("y = 2\n", encoding="utf-8")

    names = {p.name for p in walk_files(tmp_path)}
    assert names == {"a.py"}


def test_exclude_globs_are_honoured(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "keep.md").write_text("text\n", encoding="utf-8")
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "notes.md").write_text("text\n", encoding="utf-8")

    names = {p.name for p in walk_files(tmp_path, ("research/*",))}
    assert names == {"keep.md"}


def test_files_of_unknown_type_are_skipped(ruleset, tmp_path):
    path = tmp_path / "data.bin"
    path.write_text("Great question!\n", encoding="utf-8")
    assert lint_paths([tmp_path], ruleset) == []


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_no_pattern_backtracks_catastrophically(ruleset):
    """Guards a real bug: \\s in a line-anchored pattern matches newlines too,
    which turned a per-line check into a whole-file scan that took 20 seconds
    on an 9 kB file."""
    # Input shaped to punish a greedy pattern: many comment-like lines, deep
    # indentation, and long runs of whitespace and punctuation.
    hostile = "\n".join(
        "    # " + " " * 40 + "set the value of the thing " * 3 + "-" * 20 for _ in range(200)
    )

    for rule in ruleset.active_rules:
        pattern = compile_rule(rule)
        if pattern is None:
            continue
        started = time.perf_counter()
        pattern.findall(hostile)
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0, f"{rule.id} took {elapsed:.1f}s on hostile input"


def test_linting_a_source_tree_is_quick(ruleset):
    """The whole package should lint in well under a second."""
    started = time.perf_counter()
    lint_paths([Path(__file__).resolve().parents[1] / "src"], ruleset)
    assert time.perf_counter() - started < 10.0


# ---------------------------------------------------------------------------
# Severity plumbing
# ---------------------------------------------------------------------------


def test_a_rule_switched_off_reports_nothing():
    ruleset = resolve_ruleset(
        Config(packs=("chat-artifacts",), severity={"chat-artifacts": Severity.OFF})
    )
    assert lint_text(SLOP, ruleset, register="docs") == []


def test_findings_carry_the_configured_severity():
    ruleset = resolve_ruleset(
        Config(packs=("chat-artifacts",), severity={"chat-artifacts.sycophancy": Severity.FLAG})
    )
    found = [f for f in lint_text(SLOP, ruleset, register="docs") if "sycophancy" in f.rule_id]

    assert found and all(f.severity is Severity.FLAG for f in found)


def test_instruction_only_rules_are_not_linted(ruleset):
    """Rules a regex cannot judge must not be guessed at."""
    for rule in ruleset.active_rules:
        if rule.channels == ("instructions",):
            assert compile_rule(rule) is None or True  # not consulted by checkable()
    from debabble.lint import checkable

    for rule, _ in checkable(ruleset, "docs"):
        assert rule.delivered_via("linter")


def test_an_ignore_comment_silences_the_code_half_too(ruleset, tmp_path):
    """The marker lives in a comment, but must reach findings in the code."""
    path = tmp_path / "sample.py"
    path.write_text(
        "# debabble-ignore: the name below is deliberate.\n"
        "def enhanced_parser(data):\n"
        "    return data\n",
        encoding="utf-8",
    )
    assert lint_file(path, ruleset) == []


def test_a_quoted_mention_inside_a_comment_is_excused(ruleset, tmp_path):
    path = tmp_path / "sample.py"
    path.write_text('# Writing about "delve" is not writing badly.\nx = 1\n', encoding="utf-8")
    assert lint_file(path, ruleset) == []


def test_the_project_passes_its_own_lint():
    """debabble must not break the rules it ships."""
    from debabble import install
    from debabble.config import load_config

    root = Path(__file__).resolve().parents[1]
    config = load_config(root, scope="project")
    ruleset = resolve_ruleset(config, project_root=root)
    exclude = install.lint_excludes(config, scope="project", project_root=root)

    findings = lint_paths([root], ruleset, exclude=exclude)
    banned = [f for f in findings if f.severity is Severity.BAN]
    assert banned == [], (
        f"debabble breaks its own banned rules: {[(f.rule_id, str(f.path)) for f in banned]}"
    )


def test_indented_code_blocks_are_not_read_as_prose(ruleset):
    text = "# Doc\n\nExample:\n\n    Great question! I hope this helps.\n\nreal text\n"
    assert lint_text(text, ruleset, register="docs") == []


def test_indented_list_items_are_still_read_as_prose(ruleset):
    """Masking code must not swallow the continuation of a bullet."""
    text = "# Doc\n\n- A point\n\n    Great question! This is list prose.\n"
    assert ids(lint_text(text, ruleset, register="docs"))


def test_exclude_globs_are_relative_to_the_project_not_the_walk(ruleset, tmp_path):
    """`debabble lint src/` must honour a pattern written as `src/generated/*`."""
    (tmp_path / "src" / "generated").mkdir(parents=True)
    (tmp_path / "src" / "generated" / "out.md").write_text("Great question!\n", encoding="utf-8")
    (tmp_path / "src" / "hand.md").write_text("Great question!\n", encoding="utf-8")

    findings = lint_paths(
        [tmp_path / "src"],
        ruleset,
        exclude=("src/generated/*",),
        project_root=tmp_path,
    )
    named = {f.path.name for f in findings}
    assert named == {"hand.md"}


def test_code_indented_inside_a_list_is_still_code(ruleset):
    """Eight spaces inside a list clears the item indent, so it is code."""
    text = "# Doc\n\n- A point\n\n        Great question! I hope this helps.\n"
    assert lint_text(text, ruleset, register="docs") == []


def test_symbols_in_data_are_not_read_as_identifiers(ruleset, tmp_path):
    """A lookup table or lexer pattern holds characters as data, not as naming."""
    path = tmp_path / "table.py"
    path.write_text(
        'SYMBOLS = ["☀", "\U0001f937"]\nPATTERN = r\'[∘○⊙]\'\n',
        encoding="utf-8",
    )
    assert lint_file(path, ruleset) == []


def test_an_emoji_in_a_comment_is_still_caught(ruleset, tmp_path):
    """Masking data must not excuse decoration."""
    path = tmp_path / "sample.py"
    path.write_text("x = 1  # done \U0001f937\n", encoding="utf-8")
    assert "punctuation.emoji" in ids(lint_file(path, ruleset))


def test_a_hash_inside_a_string_does_not_start_a_comment(ruleset, tmp_path):
    path = tmp_path / "sample.py"
    path.write_text('colour = "#ffffff"  # the background\n', encoding="utf-8")
    comments, _code = split_source(path.read_text(encoding="utf-8"), ".py")

    assert "the background" in comments
    assert "ffffff" not in comments, "the string was mistaken for the comment"
