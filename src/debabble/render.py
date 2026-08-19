"""Turning rules into the instruction text that gets installed.

The output is plain Markdown, because every tool debabble writes to reads plain
Markdown. Two styles exist: ``compact`` states the rules, ``full`` adds a
wrong/right example pair for each. Instruction files are paid for out of a
model's context window, so compact is the default.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import RuleSet, Severity

TITLE = "Writing rules: no AI-speak"

# Ban lists alone teach a model to evade rather than to write well, so every
# rendered file opens by saying what good looks like.
PREAMBLE = """Apply these rules to everything you write here: prose, documentation, code
comments, and commit messages.

Write plainly and specifically. Prefer "is" and "has" to showier verbs. Prefer a
concrete number, name, or example to an intensity adjective. Vary sentence
length. End on the last real point rather than a summary. Repeat a noun instead
of cycling through synonyms for it. Make only claims the work supports. Read
what you wrote before you finish."""

BAN_HEADING = "Never"
FLAG_HEADING = "Use sparingly"
FLAG_NOTE = (
    "Each of these is fine once. They read as machine writing when they cluster, "
    "so keep them rare and deliberate."
)

# A term list longer than this is summarised rather than printed in full, so a
# single vocabulary rule cannot swamp the file.
_MAX_TERMS_COMPACT = 60


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Rendered text plus what had to be given up to fit a size budget."""

    text: str
    style: str
    dropped_examples: bool = False
    dropped_packs: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.text)

    @property
    def was_trimmed(self) -> bool:
        return self.dropped_examples or bool(self.dropped_packs)


def _format_terms(terms: tuple[str, ...], *, limit: int | None) -> str:
    shown = list(terms)
    suffix = ""
    if limit is not None and len(shown) > limit:
        shown = shown[:limit]
        suffix = f", and {len(terms) - limit} more"
    return ", ".join(shown) + suffix


def _render_rule(rule, *, style: str, term_limit: int | None) -> list[str]:
    """One rule as a bullet: a short bold label, then what to do about it."""
    lines = [f"- **{rule.display_title}.** {rule.instruction.strip()}"]

    if rule.terms:
        label = "Never use" if rule.severity is Severity.BAN else "Watch for"
        lines.append(f"  {label}: {_format_terms(rule.terms, limit=term_limit)}.")

    if rule.suggest and rule.severity is Severity.BAN:
        lines.append(f"  Prefer: {', '.join(rule.suggest)}.")

    if style == "full" and rule.wrong and rule.right:
        lines.append(f"  - No: {rule.wrong.strip()}")
        lines.append(f"  - Yes: {rule.right.strip()}")

    return lines


def _instruction_rules(ruleset: RuleSet, severity: Severity, skip_packs: frozenset[str]) -> list:
    """Rules of one severity that are delivered as instructions, in pack order."""
    out = []
    for pack in ruleset.packs:
        if pack.id in skip_packs:
            continue
        for rule in pack.active_rules:
            if rule.severity is severity and rule.delivered_via("instructions"):
                out.append(rule)
    return out


def render_body(
    ruleset: RuleSet,
    *,
    style: str = "compact",
    include_examples: bool | None = None,
    skip_packs: frozenset[str] = frozenset(),
) -> str:
    """Render the rules as Markdown, without any tool-specific header."""
    if include_examples is None:
        include_examples = style == "full"
    effective_style = "full" if include_examples else "compact"
    term_limit = None if style == "full" else _MAX_TERMS_COMPACT

    sections = [f"# {TITLE}", "", PREAMBLE.strip()]

    # Grouping by severity rather than by pack gives the reader one absolute
    # list and one judgement list, which is the distinction that changes how a
    # rule should be applied.
    banned = _instruction_rules(ruleset, Severity.BAN, skip_packs)
    if banned:
        sections.extend(["", f"## {BAN_HEADING}", ""])
        for rule in banned:
            sections.extend(_render_rule(rule, style=effective_style, term_limit=term_limit))

    flagged = _instruction_rules(ruleset, Severity.FLAG, skip_packs)
    if flagged:
        sections.extend(["", f"## {FLAG_HEADING}", "", FLAG_NOTE, ""])
        for rule in flagged:
            sections.extend(_render_rule(rule, style=effective_style, term_limit=term_limit))

    return "\n".join(sections).rstrip() + "\n"


def render(
    ruleset: RuleSet,
    *,
    style: str = "compact",
    budget: int | None = None,
) -> RenderResult:
    """Render the rules, trimming deterministically if a size budget demands it.

    Trimming order is fixed so that the same inputs always produce the same
    output: examples go first, then whole packs in ascending priority, which
    leaves the highest-value rules (chat artifacts, your own rules) standing
    longest.
    """
    text = render_body(ruleset, style=style)
    if budget is None or len(text) <= budget:
        return RenderResult(text=text, style=style)

    # Step one: drop the examples.
    if style == "full":
        text = render_body(ruleset, style=style, include_examples=False)
        if len(text) <= budget:
            return RenderResult(text=text, style=style, dropped_examples=True)
    dropped_examples = style == "full"

    # Step two: drop whole packs, least important first.
    order = sorted(ruleset.packs, key=lambda p: (p.priority, p.id))
    skip: set[str] = set()
    for pack in order:
        skip.add(pack.id)
        text = render_body(ruleset, style=style, include_examples=False, skip_packs=frozenset(skip))
        if len(text) <= budget:
            return RenderResult(
                text=text,
                style=style,
                dropped_examples=dropped_examples,
                dropped_packs=tuple(sorted(skip)),
            )

    # Nothing fits. Return the smallest thing we can build and let the caller
    # report it; silently writing a truncated file would be worse.
    return RenderResult(
        text=text,
        style=style,
        dropped_examples=dropped_examples,
        dropped_packs=tuple(sorted(skip)),
    )


def render_rewrite_command(ruleset: RuleSet, *, style: str = "compact") -> str:
    """The body of the /debabble slash command: rules plus an explicit task.

    The command file is the one place the rules are used to *rewrite* existing
    text rather than to shape new writing, so it needs a task instruction and an
    argument placeholder.
    """
    body = render_body(ruleset, style=style)
    task = """
## Task

Rewrite the text below so it follows every rule above.

Preserve the meaning, the technical content, and the author's intent exactly.
Do not add information, and do not remove information. Change only the writing.
If the text already follows the rules, say so and leave it alone.

Output only the rewritten text, with no preamble and no commentary.

$ARGUMENTS
""".strip()
    return f"{body}\n{task}\n"


__all__ = ["PREAMBLE", "TITLE", "RenderResult", "render", "render_body", "render_rewrite_command"]
