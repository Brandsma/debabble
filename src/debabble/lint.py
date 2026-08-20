"""Checking text against the same rules that get installed.

This is deliberately a regex-and-counting engine, not a language model and not a
parser. It reports only what it can point at: a rule, a file, a line, and the
text that matched. Patterns a regex cannot judge (rhythm, whether a docstring is
worth writing) are marked ``channels = ["instructions"]`` in their pack and are
skipped here rather than guessed at.

Two things keep the false-positive rate honest. Code is masked before prose
rules run, so a document quoting bad writing is not accused of it. And rules
with a ``max`` are counted per paragraph, section, or document rather than
reported on sight.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from . import paths
from .managed_block import fenced_spans
from .models import Rule, RuleSet, Severity

# Suppress the next line, or the line it appears on.
IGNORE = re.compile(r"debabble[-:]\s?ignore", re.IGNORECASE)

_MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdx", ".rst", ".txt"}
_COMMIT_NAMES = {"COMMIT_EDITMSG", "MERGE_MSG", "TAG_EDITMSG"}

# Line comment markers by file type, used to pull comments out of source.
_LINE_COMMENTS = {
    ".py": ("#",),
    ".rb": ("#",),
    ".sh": ("#",),
    ".bash": ("#",),
    ".zsh": ("#",),
    ".toml": ("#",),
    ".yaml": ("#",),
    ".yml": ("#",),
    ".js": ("//",),
    ".jsx": ("//",),
    ".ts": ("//",),
    ".tsx": ("//",),
    ".go": ("//",),
    ".rs": ("//",),
    ".java": ("//",),
    ".c": ("//",),
    ".h": ("//",),
    ".cpp": ("//",),
    ".cs": ("//",),
    ".swift": ("//",),
    ".kt": ("//",),
    ".php": ("//", "#"),
    ".sql": ("--",),
    ".lua": ("--",),
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule matching one piece of text."""

    rule_id: str
    severity: Severity
    line: int
    column: int
    matched: str
    message: str
    path: Path | None = None

    def as_dict(self) -> dict:
        return {
            "rule": self.rule_id,
            "severity": str(self.severity),
            "path": str(self.path) if self.path else None,
            "line": self.line,
            "column": self.column,
            "matched": self.matched,
            "message": self.message,
        }


# Working out what kind of text we are looking at


def registers_for_path(path: Path) -> tuple[str, ...]:
    """Which registers apply to a file, based on its name and extension."""
    if path.name in _COMMIT_NAMES:
        return ("commits",)
    suffix = path.suffix.lower()
    if suffix in _MARKDOWN_SUFFIXES:
        return ("prose", "docs")
    if suffix in _LINE_COMMENTS:
        return ("comments", "code")
    return ()


# Masking: replacing text a rule should not see, without moving anything


def blank_text(text: str) -> str:
    """Replace a span with spaces so every later offset still lines up."""
    return re.sub(r"[^\n]", " ", text)


def _blank(match: re.Match) -> str:
    return blank_text(match.group(0))


def blank_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Blank the given ranges, keeping the text the same length."""
    if not spans:
        return text
    out = list(text)
    for start, end in spans:
        out[start:end] = blank_text(text[start:end])
    return "".join(out)


_INLINE_CODE = re.compile(r"`[^`\n]+`")

# A word or two inside quotation marks is a word being named, not a word being
# used: writing about "delve" is not writing badly. Longer quotations are left
# alone, because those are real sentences that the rules should still see.
# debabble-ignore: the curly quotes below are the characters being matched.
_MENTION = re.compile(r"[\"“‘']\s*[\w-]+(?:\s+[\w-]+){0,2}\s*[\"”’']")


def mask_indented_code(text: str) -> str:
    """Blank out indented code blocks, without swallowing indented list items.

    A run of four-space-indented lines after a blank line is a code block in
    Markdown, but so is the continuation of a bullet. Requiring that the run
    does not begin with a list marker keeps prose inside lists readable to the
    rules, at the cost of missing findings in the rare code block that opens
    with something that looks like a bullet.
    """
    lines = text.splitlines(keepends=True)
    out = list(lines)
    previous_blank = True
    in_block = False
    in_list = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if not in_block:
                previous_blank = True
            continue

        indent = len(line) - len(line.lstrip(" \t"))
        # Inside a list, four spaces is the continuation of an item; code has
        # to clear the item's own indent first. Outside one, four is code.
        threshold = 8 if in_list else 4
        is_list_marker = re.match(r"[ \t]*(?:[-*+]|\d+[.)])\s", line) is not None

        if is_list_marker and indent < threshold:
            in_list = True
            in_block = False
            previous_blank = False
            continue

        if indent < 4:
            # Back at the left margin: no longer in a list or a code block.
            in_list = False
            in_block = False
            previous_blank = False
            continue

        if in_block or (previous_blank and indent >= threshold):
            in_block = True
            out[i] = blank_text(line)
        previous_blank = False

    return "".join(out)


def mask_markdown(text: str) -> str:
    """Hide code and quoted mentions from prose rules.

    Without this, any document that quotes bad writing as an example is accused
    of it, including debabble's own README.
    """
    masked = blank_spans(text, fenced_spans(text))
    masked = mask_indented_code(masked)
    masked = _INLINE_CODE.sub(_blank, masked)
    masked = _MENTION.sub(_blank, masked)
    return masked


_HEADING_LINE = re.compile(r"^#{1,6} .*$", re.MULTILINE)


def mask_for_scope(text: str, scope: str) -> str:
    """Hide the part of a document a scoped rule should not look at.

    A rule scoped to headings must not fire on body text that happens to use
    the same word, and the other way round.
    """
    if scope == "heading":
        # Blank everything that is not a heading line.
        headings = [(m.start(), m.end()) for m in _HEADING_LINE.finditer(text)]
        gaps, cursor = [], 0
        for start, end in headings:
            gaps.append((cursor, start))
            cursor = end
        gaps.append((cursor, len(text)))
        return blank_spans(text, gaps)
    if scope == "body":
        return _HEADING_LINE.sub(_blank, text)
    return text


def mask_strings(text: str) -> str:
    """Blank out string literals, keeping every offset where it was.

    A small scanner rather than a regex: quoting rules with escapes and triple
    quotes are the kind of thing a pattern gets subtly wrong, and this has to be
    right for line numbers to mean anything.
    """
    out = list(text)
    i, length = 0, len(text)

    while i < length:
        char = text[i]
        if char not in "\"'":
            i += 1
            continue

        triple = text[i : i + 3]
        quote, size = (triple, 3) if triple in ('"""', "'''") else (char, 1)
        j = i + size

        while j < length:
            if text[j] == "\\":
                j += 2
                continue
            if text.startswith(quote, j):
                j += size
                break
            # A single-quoted literal cannot span lines; treat the newline as
            # the end so an apostrophe in a comment does not swallow the file.
            if size == 1 and text[j] == "\n":
                break
            j += 1
        else:
            j = length

        for k in range(i, min(j, length)):
            if out[k] != "\n":
                out[k] = " "
        i = max(j, i + 1)

    return "".join(out)


def split_source(text: str, suffix: str) -> tuple[str, str]:
    """Separate a source file into its comments and its code.

    Returns two strings the same length as the original, one holding only the
    comment text and one holding only the code, so line and column numbers stay
    correct in both. String literals are masked out of both: they are neither
    comments nor identifiers, and treating them as prose produces noise.
    """
    markers = _LINE_COMMENTS.get(suffix.lower(), ("#",))
    without_strings = mask_strings(text)

    comment_chars: list[str] = []
    code_chars: list[str] = []

    for masked, original in zip(
        without_strings.splitlines(keepends=True), text.splitlines(keepends=True), strict=False
    ):
        # Comment markers are located in the string-masked line, so a '#' inside
        # a literal does not look like the start of a comment.
        start = None
        for marker in markers:
            found = masked.find(marker)
            if found != -1 and (start is None or found < start):
                start = found

        if start is None:
            comment_chars.append(blank_text(original))
            # The code half is the masked line: a symbol in a lookup table or a
            # lexer pattern is data, not an identifier anybody chose.
            code_chars.append(masked)
        else:
            comment_chars.append(blank_text(original[:start]) + original[start:])
            code_chars.append(masked[:start] + blank_text(masked[start:]))

    return "".join(comment_chars), "".join(code_chars)


# Compiling rules into patterns


# Word lists and phrases are written with a typewriter apostrophe, but models
# emit the typographic one constantly. Without this, "You're absolutely right"
# is caught and "You’re absolutely right" is not.
_APOSTROPHES = "['’ʼ‘]"


def _apostrophe_tolerant(escaped: str) -> str:
    return escaped.replace(r"\'", _APOSTROPHES).replace("'", _APOSTROPHES)


def compile_rule(rule: Rule) -> re.Pattern | None:
    """The regex a rule matches with, or None if it is not machine-checkable.

    Word and phrase lists are written in lower case and matched without regard
    to case. A hand-written pattern is taken literally: rules that detect Title
    Case, ALL CAPS, or an identifier prefix depend on case, so a pattern only
    ignores it when its author asked for that with an inline ``(?i)``.
    """
    if rule.kind == "regex" and rule.pattern:
        return re.compile(rule.pattern, re.MULTILINE)
    if rule.kind == "wordlist" and rule.words:
        alternatives = "|".join(
            _apostrophe_tolerant(re.escape(w)) for w in sorted(rule.words, key=len, reverse=True)
        )
        return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)
    if rule.kind == "phrase" and rule.phrases:
        # Allow any run of whitespace, including a line break, inside a phrase.
        alternatives = "|".join(
            r"\s+".join(_apostrophe_tolerant(re.escape(part)) for part in phrase.split())
            for phrase in sorted(rule.phrases, key=len, reverse=True)
        )
        return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)
    return None


@lru_cache(maxsize=32)
def checkable(ruleset: RuleSet, register: str) -> tuple[tuple[Rule, re.Pattern], ...]:
    """Active rules for a register that the linter can actually check.

    Cached because this is per-file work that does not vary per file: building
    the alternations for 214 words and 273 phrases costs more than checking a
    small file, and a tree walk calls it twice for every file it visits.
    """
    return tuple(
        (rule, pattern)
        for rule in ruleset.active_rules
        if rule.applies_to(register)
        and rule.delivered_via("linter")
        and (pattern := compile_rule(rule)) is not None
    )


# Segmenting, for density rules


def _segments(text: str, unit: str) -> list[tuple[int, int]]:
    """Spans of text that a `max` is counted within."""
    if unit == "document" or not text:
        return [(0, len(text))]

    if unit == "paragraph":
        spans, start = [], 0
        for blank in re.finditer(r"\n[ \t]*\n", text):
            spans.append((start, blank.start()))
            start = blank.end()
        spans.append((start, len(text)))
        return [s for s in spans if s[1] > s[0]]

    if unit == "section":
        starts = [m.start() for m in _HEADING_LINE.finditer(text)]
        if not starts:
            return [(0, len(text))]
        bounds = [0, *starts, len(text)]
        return [
            (bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]
        ]

    # "words": one span, with the allowance scaled by length instead.
    return [(0, len(text))]


def _allowance(rule: Rule, text: str) -> int:
    """How many matches are tolerated before anything is reported."""
    if rule.max is None:
        return 0
    if rule.unit != "words":
        return rule.max
    words = len(re.findall(r"\b\w+\b", text)) or 1
    return max(rule.max, round(rule.max * words / rule.per_words))


# Linting


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def _position(starts: list[int], index: int) -> tuple[int, int]:
    low, high = 0, len(starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if starts[mid] <= index:
            low = mid
        else:
            high = mid - 1
    return low + 1, index - starts[low] + 1


def _suppressed_lines(text: str) -> set[int]:
    """Lines silenced by a debabble-ignore comment, and the line after it."""
    silenced: set[int] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if IGNORE.search(line):
            silenced.add(number)
            silenced.add(number + 1)
    return silenced


def lint_text(
    text: str,
    ruleset: RuleSet,
    *,
    register: str = "prose",
    path: Path | None = None,
    mask: bool = True,
    silenced: set[int] | None = None,
) -> list[Finding]:
    """Check one piece of text in one register.

    ``silenced`` lets a caller supply the suppressed line numbers separately.
    That matters for source files: an ignore comment lives in the comment half,
    so it has to be found before the halves are split, or it could never
    silence anything in the code half.
    """
    if not text:
        return []

    if mask and register in ("prose", "docs"):
        searchable = mask_markdown(text)
    elif register in ("comments", "commits"):
        # Comments and commit messages are prose, so a quoted word is a
        # mention there too. They have no code fences to worry about.
        searchable = _MENTION.sub(_blank, text)
    else:
        searchable = text
    starts = _line_starts(text)
    if silenced is None:
        silenced = _suppressed_lines(text)
    findings: list[Finding] = []

    for rule, pattern in checkable(ruleset, register):
        scoped = mask_for_scope(searchable, rule.scope)
        for start, end in _segments(scoped, rule.unit):
            window = scoped[start:end]
            matches = list(pattern.finditer(window))
            if not matches:
                continue
            # A rule with a max reports only what exceeds the allowance.
            over = matches[_allowance(rule, window) :] if rule.max is not None else matches
            for match in over:
                line, column = _position(starts, start + match.start())
                if line in silenced:
                    continue
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        severity=rule.severity,
                        line=line,
                        column=column,
                        matched=match.group(0).strip(),
                        message=rule.instruction,
                        path=path,
                    )
                )

    findings.sort(key=lambda f: (f.line, f.column, f.rule_id))
    return findings


def lint_file(path: Path, ruleset: RuleSet) -> list[Finding]:
    """Check one file, in whichever registers its type calls for."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    registers = registers_for_path(path)
    if not registers:
        return []

    findings: list[Finding] = []
    silenced = _suppressed_lines(text)
    if "comments" in registers or "code" in registers:
        comments, code = split_source(text, path.suffix)
        for half, register in ((comments, "comments"), (code, "code")):
            findings += lint_text(
                half, ruleset, register=register, path=path, mask=False, silenced=silenced
            )
    else:
        for register in registers:
            findings += lint_text(text, ruleset, register=register, path=path, silenced=silenced)

    # A rule in two registers should still only be reported once per position.
    seen: set[tuple] = set()
    unique = []
    for finding in sorted(findings, key=lambda f: (f.line, f.column, f.rule_id)):
        key = (finding.rule_id, finding.line, finding.column)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".debabble",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "site-packages",
}


def walk_files(
    root: Path, exclude: tuple[str, ...] = (), *, project_root: Path | None = None
) -> list[Path]:
    """Every file under a directory that is worth checking.

    Directories in the skip list are pruned during the walk rather than
    filtered afterwards, which matters: descending into a virtual environment
    to throw the results away takes longer than the linting does.
    """
    # Resolve the base once. Doing it per file made an excluded tree of 2,000
    # files take 674 ms, almost all of it in Path.resolve.
    base = (project_root or root).resolve()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        directory = Path(dirpath)
        for name in sorted(filenames):
            path = directory / name
            if not registers_for_path(path):
                continue
            if exclude and matches_exclude(paths.relative_posix(path, base), exclude):
                continue
            found.append(path)
    return found


def matches_exclude(relative: str, exclude: tuple[str, ...]) -> bool:
    """Whether a project-relative path matches one of the exclude globs."""
    return any(
        fnmatch(relative, pattern) or fnmatch(relative, f"{pattern.rstrip('/')}/*")
        for pattern in exclude
    )


def is_excluded(path: Path, root: Path, exclude: tuple[str, ...]) -> bool:
    """Whether a path matches one of the configured exclude globs."""
    if not exclude:
        return False
    return matches_exclude(paths.relative_posix(path, root), exclude)


def lint_paths(
    paths: list[Path],
    ruleset: RuleSet,
    *,
    exclude: tuple[str, ...] = (),
    project_root: Path | None = None,
) -> list[Finding]:
    """Check files and directories, skipping anything unreadable or irrelevant.

    Exclude globs are written relative to the project, so they mean the same
    thing whether you check the whole tree or one subdirectory of it.
    """
    root = project_root or Path.cwd()
    findings: list[Finding] = []
    for path in paths:
        if path.is_dir():
            for child in walk_files(path, exclude, project_root=root):
                findings += lint_file(child, ruleset)
        elif path.is_file() and not is_excluded(path, root, exclude):
            findings += lint_file(path, ruleset)
    return findings


def summarise(findings: list[Finding]) -> dict:
    """Counts every caller reports the same way."""
    banned = sum(1 for f in findings if f.severity is Severity.BAN)
    return {
        "findings": [f.as_dict() for f in findings],
        "banned": banned,
        "flagged": len(findings) - banned,
        "clean": not findings,
    }


def worst_severity(findings: list[Finding]) -> Severity | None:
    if any(f.severity is Severity.BAN for f in findings):
        return Severity.BAN
    if findings:
        return Severity.FLAG
    return None


__all__ = [
    "Finding",
    "compile_rule",
    "lint_file",
    "lint_paths",
    "lint_text",
    "mask_markdown",
    "registers_for_path",
    "split_source",
    "summarise",
    "worst_severity",
]
