"""The core data types: severities, rules, and packs.

A *rule* is one editable unit of style guidance. A *pack* is a themed group of
rules shipped as a single TOML file. Everything a user can change about a rule
lives in the fields below, so both the TOML files and the config overrides speak
exactly the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from .errors import PackError

# Where a rule applies. A file's type decides which registers are checked.
REGISTERS = ("prose", "docs", "comments", "commits", "code")

# Where a rule is delivered. Most rules do both; some only make sense as
# generation-time guidance (rhythm, docstring judgement) and some only as
# after-the-fact lint checks (empty except blocks).
CHANNELS = ("instructions", "linter")

# How a rule is matched and phrased.
KINDS = ("wordlist", "phrase", "regex", "guidance")

# What a `max` count is measured against.
UNITS = ("paragraph", "section", "document", "words")

# Which part of a document a rule looks at.
SCOPES = ("body", "heading", "any")


class Severity(StrEnum):
    """How hard a rule pushes.

    ``ban`` is absolute: never do this. ``flag`` is density guidance: fine
    occasionally, a tell in clusters. ``off`` disables the rule entirely.

    Users change severity per rule or per pack, in ``debabble.toml`` or with
    ``--severity ID=LEVEL`` on the command line.
    """

    BAN = "ban"
    FLAG = "flag"
    OFF = "off"

    @property
    def is_active(self) -> bool:
        return self is not Severity.OFF

    @classmethod
    def parse(cls, value: object, *, where: str = "severity") -> Severity:
        """Parse a severity from user input, with a message naming the options."""
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        # A few friendly synonyms, because people type what they mean.
        aliases = {
            "error": cls.BAN,
            "never": cls.BAN,
            "warn": cls.FLAG,
            "warning": cls.FLAG,
            "disabled": cls.OFF,
            "none": cls.OFF,
            "false": cls.OFF,
        }
        if text in aliases:
            return aliases[text]
        try:
            return cls(text)
        except ValueError:
            options = ", ".join(s.value for s in cls)
            raise PackError(
                f"{where}: {value!r} is not a severity. Use one of: {options}."
            ) from None


@dataclass(frozen=True, slots=True)
class Rule:
    """One editable piece of style guidance.

    Only ``id`` and ``instruction`` are required. Everything else has a sensible
    default, so a custom rule can be three lines of TOML.
    """

    id: str
    instruction: str
    title: str = ""
    severity: Severity = Severity.FLAG
    kind: str = "guidance"
    registers: tuple[str, ...] = ("prose", "docs")
    channels: tuple[str, ...] = ("instructions", "linter")
    scope: str = "any"

    # Matching, by kind.
    words: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()
    pattern: str = ""

    # Density: at most `max` matches per `unit`. `per_words` sizes the window
    # when unit == "words" (for example max=1, unit="words", per_words=500).
    max: int | None = None
    unit: str = "paragraph"
    per_words: int = 500

    # Teaching material. `wrong`/`right` are shown in the "full" render style.
    wrong: str = ""
    right: str = ""
    why: str = ""
    suggest: tuple[str, ...] = ()

    # `fix = "safe"` opts a rule into mechanical `debabble lint --fix`
    # substitutions (the first `suggest` entry, or a literal replacement).
    fix: str = ""
    replacement: str = ""

    # Vocabulary tells drift by model generation; era tags let packs be refreshed
    # without guesswork about which entries are stale.
    era: str = ""

    @property
    def pack(self) -> str:
        """The pack this rule belongs to, taken from its qualified id."""
        return self.id.split(".", 1)[0]

    @property
    def short_id(self) -> str:
        """The rule's id within its pack."""
        _, _, rest = self.id.partition(".")
        return rest or self.id

    @property
    def display_title(self) -> str:
        return self.title or self.short_id.replace("-", " ").capitalize()

    @property
    def terms(self) -> tuple[str, ...]:
        """Every literal string this rule matches on, whatever its kind."""
        return self.words + self.phrases

    def applies_to(self, register: str) -> bool:
        return register in self.registers

    def delivered_via(self, channel: str) -> bool:
        return channel in self.channels

    def with_severity(self, severity: Severity) -> Rule:
        return replace(self, severity=severity)


@dataclass(frozen=True, slots=True)
class Pack:
    """A themed group of rules, shipped as one TOML file."""

    id: str
    title: str
    description: str
    rules: tuple[Rule, ...]
    version: str = ""
    references: tuple[str, ...] = ()
    # Packs enabled by default are what a fresh `debabble apply` installs.
    default: bool = True
    # Higher priority survives longer when output has to fit a size budget.
    priority: int = 50
    # Where the pack came from, for `debabble packs` and error messages.
    source: str = "built-in"

    @property
    def active_rules(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.severity.is_active)

    def rule(self, rule_id: str) -> Rule | None:
        qualified = rule_id if "." in rule_id else f"{self.id}.{rule_id}"
        for r in self.rules:
            if r.id == qualified:
                return r
        return None


@dataclass(frozen=True, slots=True)
class RuleSet:
    """The packs and rules in effect after config has been applied."""

    packs: tuple[Pack, ...]

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(r for p in self.packs for r in p.rules)

    @property
    def active_rules(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.severity.is_active)

    def for_channel(self, channel: str) -> tuple[Rule, ...]:
        return tuple(r for r in self.active_rules if r.delivered_via(channel))

    def for_register(self, register: str) -> tuple[Rule, ...]:
        return tuple(r for r in self.active_rules if r.applies_to(register))

    def rule(self, rule_id: str) -> Rule | None:
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None

    def pack(self, pack_id: str) -> Pack | None:
        for p in self.packs:
            if p.id == pack_id:
                return p
        return None

    def counts(self) -> dict[Severity, int]:
        counts = {s: 0 for s in Severity}
        for r in self.rules:
            counts[r.severity] += 1
        return counts


def validate_choice(value: str, allowed: tuple[str, ...], *, where: str) -> str:
    """Check a single enum-ish string, with a message that lists the options."""
    if value not in allowed:
        raise PackError(f"{where}: {value!r} is not valid. Use one of: {', '.join(allowed)}.")
    return value


def validate_choices(values: object, allowed: tuple[str, ...], *, where: str) -> tuple[str, ...]:
    """Check a list of enum-ish strings, accepting a bare string as a one-item list."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise PackError(f"{where}: expected a list of strings, got {type(values).__name__}.")
    return tuple(validate_choice(str(v), allowed, where=where) for v in values)


__all__ = [
    "CHANNELS",
    "KINDS",
    "REGISTERS",
    "SCOPES",
    "UNITS",
    "Pack",
    "Rule",
    "RuleSet",
    "Severity",
    "validate_choice",
    "validate_choices",
]
