"""Exceptions raised by debabble.

Every error carries a message written for the person at the terminal, not for a
log file. The CLI prints ``str(err)`` and exits non-zero.
"""

from __future__ import annotations


class DebabbleError(Exception):
    """Base class for every error debabble raises on purpose."""


class PackError(DebabbleError):
    """A rule pack could not be loaded or is invalid."""


class ConfigError(DebabbleError):
    """A configuration file is invalid, or asks for something that does not exist."""


class TargetError(DebabbleError):
    """An install target could not be written, read, or resolved."""


class BlockError(DebabbleError):
    """A managed block in a file is ambiguous, so debabble will not touch it."""
