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

BEGIN = "<!-- BEGIN debabble -->"
END = "<!-- END debabble -->"
NOTE = "<!-- Managed by debabble. Edits between these markers are overwritten. -->"

_BLOCK = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END),
    re.DOTALL,
)


def wrap(body: str) -> str:
    """Wrap rendered content in the markers, with a note for whoever opens the file."""
    return f"{BEGIN}\n{NOTE}\n\n{body.strip()}\n\n{END}"


def contains(text: str) -> bool:
    return _BLOCK.search(text) is not None


def extract(text: str) -> str | None:
    """The current managed block, markers included, or None if there is not one."""
    match = _BLOCK.search(text)
    return match.group(0) if match else None


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

    if _BLOCK.search(normalised):
        # re.sub would interpret backslashes in the replacement, so splice by index.
        match = _BLOCK.search(normalised)
        assert match is not None
        updated = normalised[: match.start()] + block + normalised[match.end() :]
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
    match = _BLOCK.search(normalised)
    if match is None:
        return existing

    updated = normalised[: match.start()] + normalised[match.end() :]
    # Collapse the blank lines the block leaves behind.
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    updated = (updated + "\n") if updated else ""
    return updated.replace("\n", newline) if newline != "\n" and updated else updated


__all__ = ["BEGIN", "END", "NOTE", "contains", "detect_newline", "extract", "remove", "upsert", "wrap"]
