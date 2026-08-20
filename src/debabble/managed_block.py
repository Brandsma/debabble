"""Adding debabble's content to a file someone else owns, without clobbering it.

Some tools read a single instruction file that the user also writes in by hand
(``AGENTS.md``, ``GEMINI.md``, ``.hermes.md``). For those, debabble keeps its
content between two HTML comment markers and replaces only what lies between
them. HTML comments are safe here: Claude Code strips block comments before
using the file, and every other tool treats them as inert text.

Where a tool reads a directory of rule files instead, debabble owns a whole file
and none of this is needed.
"""

from __future__ import annotations

import re

from .errors import BlockError

BEGIN = "<!-- BEGIN debabble -->"
END = "<!-- END debabble -->"
NOTE = "<!-- Managed by debabble. Edits between these markers are overwritten. -->"

# Markers are only recognised on a line of their own. A mention inside a
# sentence is somebody writing about debabble, not a block to replace.
_BEGIN_LINE = re.compile(r"^[ \t]*" + re.escape(BEGIN) + r"[ \t]*$", re.MULTILINE)
_END_LINE = re.compile(r"^[ \t]*" + re.escape(END) + r"[ \t]*$", re.MULTILINE)

_FENCE = re.compile(r"^[ \t]*(```|~~~).*?(?:\n[ \t]*\1|\Z)", re.DOTALL | re.MULTILINE)


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """Ranges covered by fenced code blocks, which markers inside do not count."""
    return [(m.start(), m.end()) for m in _FENCE.finditer(text)]


def _outside_fences(matches, spans) -> list:
    return [m for m in matches if not any(s <= m.start() < e for s, e in spans)]


def find_block(text: str) -> tuple[int, int] | None:
    """Where debabble's block sits in ``text``, or None if there is not one.

    Markers written inside a fenced code block are ignored: a document that
    shows what the markers look like is documentation, not a managed block.

    Raises :class:`BlockError` rather than guessing when the markers do not form
    exactly one well-ordered pair. Guessing here means editing the wrong span of
    somebody's file.
    """
    spans = _fenced_spans(text)
    begins = _outside_fences(list(_BEGIN_LINE.finditer(text)), spans)
    ends = _outside_fences(list(_END_LINE.finditer(text)), spans)

    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise BlockError(
            f"Found {len(begins)} '{BEGIN}' and {len(ends)} '{END}' markers; "
            "debabble expects exactly one of each. Fix the markers by hand, "
            "then run apply again."
        )
    if ends[0].start() < begins[0].start():
        raise BlockError(
            f"'{END}' appears before '{BEGIN}'. Fix the markers by hand, then run apply again."
        )
    return begins[0].start(), ends[0].end()


def wrap(body: str) -> str:
    """Wrap rendered content in the markers, with a note for whoever opens the file."""
    return f"{BEGIN}\n{NOTE}\n\n{body.strip()}\n\n{END}"


def contains(text: str) -> bool:
    try:
        return find_block(text) is not None
    except BlockError:
        return True


def extract(text: str) -> str | None:
    """The current managed block, markers included, or None if there is not one."""
    found = find_block(text)
    return text[found[0] : found[1]] if found else None


def detect_newline(text: str) -> str:
    """The line ending a file already uses, so we do not mix styles into it."""
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    return "\r\n" if "\r" in text else "\n"


def upsert(existing: str, body: str) -> str:
    """Insert or replace debabble's block in ``existing``, leaving the rest alone.

    A file that has no block yet gets one appended, separated by a blank line.
    Line endings follow whatever the file already uses.
    """
    newline = detect_newline(existing)
    normalised = existing.replace("\r\n", "\n").replace("\r", "\n")
    block = wrap(body)

    found = find_block(normalised)
    if found is not None:
        start, end = found
        # Splice by index: re.sub would read backslashes in the replacement.
        updated = normalised[:start] + block + normalised[end:]
    elif normalised.strip():
        updated = normalised.rstrip("\n") + "\n\n" + block + "\n"
    else:
        updated = block + "\n"

    if not updated.endswith("\n"):
        updated += "\n"
    return updated.replace("\n", newline) if newline != "\n" else updated


def remove(existing: str) -> str:
    """Take debabble's block back out, leaving the user's content as it was."""
    newline = detect_newline(existing)
    normalised = existing.replace("\r\n", "\n").replace("\r", "\n")
    found = find_block(normalised)
    if found is None:
        return existing

    start, end = found
    updated = normalised[:start] + normalised[end:]
    # Collapse the blank lines the block leaves behind.
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    updated = (updated + "\n") if updated else ""
    return updated.replace("\n", newline) if newline != "\n" and updated else updated


__all__ = [
    "BEGIN",
    "END",
    "NOTE",
    "contains",
    "detect_newline",
    "extract",
    "remove",
    "upsert",
    "wrap",
]
