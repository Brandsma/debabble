"""Where each AI coding tool reads its rules, and how debabble writes there.

Two write strategies are used, and the choice is forced by the tool:

``own``
    The tool reads a directory of rule files, so debabble owns one file in it
    outright. Uninstalling deletes that file. Nothing a user wrote is ever at
    risk.

``block``
    The tool reads a single file the user also writes in, so debabble keeps its
    content between markers and replaces only that. See :mod:`managed_block`.

Paths were verified against each tool's current documentation. When a tool moves
its files, the fix belongs here and nowhere else.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .errors import TargetError

SCOPES = ("project", "global")

# What gets written into the file: the rules themselves, or the rewrite command.
CONTENT_RULES = "rules"
CONTENT_REWRITE = "rewrite-command"


@dataclass(frozen=True, slots=True)
class TargetFile:
    """One file debabble writes for one tool in one scope."""

    path: Path
    strategy: str = "own"
    frontmatter: tuple[tuple[str, str], ...] = ()
    budget: int | None = None
    content: str = CONTENT_RULES

    @property
    def owns_file(self) -> bool:
        return self.strategy == "own"


@dataclass(frozen=True, slots=True)
class Target:
    """One tool debabble can install into."""

    id: str
    title: str
    description: str
    resolver: Callable[[str, Path | None], list[TargetFile]]
    notes: dict[str, str] = field(default_factory=dict)
    default: bool = False

    def files(self, scope: str, project_root: Path | None) -> list[TargetFile]:
        if scope not in SCOPES:
            raise TargetError(f"Unknown scope {scope!r}. Use 'project' or 'global'.")
        if scope == "project" and project_root is None:
            raise TargetError(f"{self.id}: a project scope needs a project directory.")
        return self.resolver(scope, project_root)

    def note(self, scope: str) -> str:
        return self.notes.get(scope, "")

    def supports(self, scope: str, project_root: Path | None = None) -> bool:
        try:
            return bool(self.files(scope, project_root or Path.cwd()))
        except TargetError:
            return False


def _home_file(*parts: str) -> Path:
    return paths.home().joinpath(*parts)


def _hermes_home() -> Path:
    """Hermes reads HERMES_HOME first; its Windows installer points that at LOCALAPPDATA."""
    from_env = paths.env_dir("HERMES_HOME")
    if from_env is not None:
        return from_env
    if os.name == "nt":
        native = paths.local_app_data() / "hermes"
        # The Linux-style layout is a documented opt-in on Windows; respect it
        # when the user has actually created it.
        legacy = paths.home() / ".hermes"
        return legacy if legacy.is_dir() and not native.is_dir() else native
    return paths.home() / ".hermes"


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------


def _claude_code(scope: str, root: Path | None) -> list[TargetFile]:
    # .claude/rules/*.md is loaded at launch, at both project and user level.
    base = root / ".claude" if scope == "project" else _home_file(".claude")
    return [TargetFile(path=base / "rules" / "debabble.md")]


def _claude_command(scope: str, root: Path | None) -> list[TargetFile]:
    base = root / ".claude" if scope == "project" else _home_file(".claude")
    return [
        TargetFile(
            path=base / "commands" / "debabble.md",
            content=CONTENT_REWRITE,
            frontmatter=(
                ("description", "Rewrite text to remove AI-speak"),
                ("argument-hint", "[text or file to rewrite]"),
            ),
        )
    ]


def _cursor(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        return []  # Cursor keeps user rules in application settings, not a file.
    return [
        TargetFile(
            path=root / ".cursor" / "rules" / "debabble.mdc",
            frontmatter=(
                ("description", "Writing rules: no AI-speak"),
                ("alwaysApply", "true"),
            ),
        )
    ]


def _agents_md(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        # Codex is the tool with a global AGENTS.md.
        return [TargetFile(path=_home_file(".codex", "AGENTS.md"), strategy="block")]
    return [TargetFile(path=root / "AGENTS.md", strategy="block")]


def _copilot(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        return []
    return [
        TargetFile(
            path=root / ".github" / "instructions" / "debabble.instructions.md",
            frontmatter=(
                ("applyTo", '"**"'),
                ("description", "Writing rules: no AI-speak"),
            ),
        )
    ]


def _windsurf(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        return [
            TargetFile(
                path=_home_file(".codeium", "windsurf", "memories", "global_rules.md"),
                strategy="block",
                budget=6000,
            )
        ]
    # Cognition is migrating Windsurf to .devin/rules; prefer it where it exists.
    devin = root / ".devin"
    base = devin if devin.is_dir() else root / ".windsurf"
    return [
        TargetFile(
            path=base / "rules" / "debabble.md",
            frontmatter=(("trigger", "always_on"),),
            budget=12000,
        )
    ]


def _gemini(scope: str, root: Path | None) -> list[TargetFile]:
    path = _home_file(".gemini", "GEMINI.md") if scope == "global" else root / "GEMINI.md"
    return [TargetFile(path=path, strategy="block")]


def _hermes(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        # Hermes has no global rules file other than SOUL.md.
        return [TargetFile(path=_hermes_home() / "SOUL.md", strategy="block")]
    # .hermes.md is Hermes-native and outranks every other context file it reads.
    return [TargetFile(path=root / ".hermes.md", strategy="block")]


def _cline(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        return [TargetFile(path=_home_file("Documents", "Cline", "Rules", "debabble.md"))]
    return [TargetFile(path=root / ".clinerules" / "debabble.md")]


def _roo(scope: str, root: Path | None) -> list[TargetFile]:
    base = _home_file(".roo") if scope == "global" else root / ".roo"
    return [TargetFile(path=base / "rules" / "debabble.md")]


def _amazon_q(scope: str, root: Path | None) -> list[TargetFile]:
    if scope == "global":
        return []
    return [TargetFile(path=root / ".amazonq" / "rules" / "debabble.md")]


def _kiro(scope: str, root: Path | None) -> list[TargetFile]:
    base = _home_file(".kiro") if scope == "global" else root / ".kiro"
    return [TargetFile(path=base / "steering" / "debabble.md")]


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

TARGETS: tuple[Target, ...] = (
    Target(
        id="claude-code",
        title="Claude Code",
        description="Rules file loaded at launch, project and user scope.",
        resolver=_claude_code,
        default=True,
    ),
    Target(
        id="claude-command",
        title="Claude Code /debabble command",
        description="A slash command that rewrites existing text using these rules.",
        resolver=_claude_command,
    ),
    Target(
        id="cursor",
        title="Cursor",
        description="An always-applied project rule.",
        resolver=_cursor,
        notes={
            "global": (
                "Cursor stores user rules in its application settings, not in a file. "
                "Run `debabble render --target cursor` and paste the output into "
                "Cursor Settings > Rules."
            )
        },
    ),
    Target(
        id="agents-md",
        title="AGENTS.md",
        description="The shared standard read by Codex, Zed, Warp, Jules, and others.",
        resolver=_agents_md,
        notes={
            "project": (
                "Some tools prefer a different file when one exists: Zed reads .rules or "
                ".cursorrules first, and Codex reads AGENTS.override.md first."
            )
        },
    ),
    Target(
        id="copilot",
        title="GitHub Copilot",
        description="A path-independent instructions file applied to every request.",
        resolver=_copilot,
        notes={
            "global": (
                "VS Code reads user-scope instructions from ~/.claude/rules, so installing "
                "the claude-code target globally already covers Copilot."
            )
        },
    ),
    Target(
        id="windsurf",
        title="Windsurf",
        description="An always-on workspace rule; uses .devin/rules when that exists.",
        resolver=_windsurf,
    ),
    Target(
        id="gemini",
        title="Gemini CLI",
        description="A managed block in GEMINI.md.",
        resolver=_gemini,
    ),
    Target(
        id="hermes",
        title="Hermes",
        description="A managed block in .hermes.md, the file Hermes reads before all others.",
        resolver=_hermes,
        notes={
            "global": (
                "Hermes has no global rules file, so the block goes in SOUL.md, which it "
                "loads for every session."
            )
        },
    ),
    Target(
        id="cline",
        title="Cline",
        description="A rule file in the .clinerules directory.",
        resolver=_cline,
    ),
    Target(
        id="roo",
        title="Roo Code",
        description="A rule file in .roo/rules.",
        resolver=_roo,
    ),
    Target(
        id="amazon-q",
        title="Amazon Q Developer",
        description="A rule file in .amazonq/rules.",
        resolver=_amazon_q,
    ),
    Target(
        id="kiro",
        title="Kiro",
        description="A steering file in .kiro/steering.",
        resolver=_kiro,
    ),
)

_BY_ID = {t.id: t for t in TARGETS}


def get_target(target_id: str) -> Target:
    """Look up a target, with an error that lists the valid ones."""
    try:
        return _BY_ID[target_id]
    except KeyError:
        known = ", ".join(sorted(_BY_ID))
        raise TargetError(f"Unknown target {target_id!r}. Available targets: {known}.") from None


def all_targets() -> tuple[Target, ...]:
    return TARGETS


def default_target_ids() -> tuple[str, ...]:
    return tuple(t.id for t in TARGETS if t.default)


def format_frontmatter(fields: tuple[tuple[str, str], ...]) -> str:
    """YAML frontmatter, in the order the target declared it."""
    if not fields:
        return ""
    lines = ["---", *(f"{key}: {value}" for key, value in fields), "---", ""]
    return "\n".join(lines)


__all__ = [
    "CONTENT_REWRITE",
    "CONTENT_RULES",
    "SCOPES",
    "TARGETS",
    "Target",
    "TargetFile",
    "all_targets",
    "default_target_ids",
    "format_frontmatter",
    "get_target",
]
