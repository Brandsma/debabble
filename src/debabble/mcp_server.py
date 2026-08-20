"""An MCP server exposing the rules and the linter to any agent that speaks MCP.

This is the same rule set the CLI installs, reachable without installing
anything into a rules file. An agent can pull the rules on demand, check text it
just wrote, and ask why a particular rule exists.

Run it over stdio:

    debabble-mcp

Register it with Claude Code:

    claude mcp add debabble --scope user -- uvx --from "debabble[mcp]" debabble-mcp
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any

from . import install, paths
from .config import STYLES, Config, load_config, resolve_ruleset
from .errors import DebabbleError
from .lint import lint_paths, lint_text, summarise
from .models import REGISTERS, RuleSet
from .packs import rule_to_toml
from .render import render_body, render_rewrite_command

_MISSING_DEPENDENCY = (
    "The MCP server needs the optional 'mcp' dependency.\n"
    "Install it with:  uv tool install 'debabble[mcp]'\n"
    "or run it with:   uvx --from 'debabble[mcp]' debabble-mcp"
)

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - exercised only without the extra
    print(_MISSING_DEPENDENCY, file=sys.stderr)
    raise SystemExit(1) from None


mcp = MCPServer("debabble")


# Finding the project a request is about


def resolve_project(project_dir: str | None = None) -> Path | None:
    """Work out which project a call refers to.

    Hosts differ in what they tell a server about the workspace, so this tries
    the explicit argument first, then the variable Claude Code sets, then the
    working directory. Cursor and other hosts may launch a server from an
    unrelated directory, which is why the argument exists at all.
    """
    if project_dir:
        candidate = Path(project_dir).expanduser()
        return candidate if candidate.is_dir() else None

    from_env = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if from_env and Path(from_env).is_dir():
        return paths.find_project_root(Path(from_env))

    return paths.find_project_root()


def load_rules(project_dir: str | None = None) -> tuple[RuleSet, Config, Path | None]:
    """The rules in effect for a project, re-read on every call.

    Re-reading is deliberate: a long-lived server should notice when someone
    edits debabble.toml, and parsing a small TOML file costs nothing.
    """
    root = resolve_project(project_dir)
    config = load_config(root, scope="project")
    return resolve_ruleset(config, project_root=root), config, root


# Tools


@mcp.tool(
    description=(
        "Check text for AI-speak against the debabble rules. Returns one finding per "
        "match, with the rule, the matched text, and what to do instead."
    )
)
def lint(
    text: Annotated[str, "The text to check."],
    register: Annotated[
        str, "Which kind of text this is: prose, docs, comments, commits, or code."
    ] = "prose",
    project_dir: Annotated[
        str, "Absolute path of the project whose configuration applies. Optional."
    ] = "",
) -> dict[str, Any]:
    """Check a piece of text and report what matched."""
    if register not in REGISTERS:
        raise ValueError(f"register must be one of: {', '.join(REGISTERS)}")

    ruleset, _config, _root = load_rules(project_dir or None)
    findings = lint_text(text, ruleset, register=register)
    return summarise(findings)


@mcp.tool(
    description=(
        "Check files or directories on disk for AI-speak. Skips files debabble itself "
        "wrote and anything excluded in the project configuration."
    )
)
def lint_files(
    paths_to_check: Annotated[list[str], "File or directory paths to check."],
    project_dir: Annotated[str, "Absolute path of the project. Optional."] = "",
) -> dict[str, Any]:
    """Check files on disk and report what matched."""
    ruleset, config, root = load_rules(project_dir or None)
    exclude = install.lint_excludes(config, scope="project", project_root=root)
    findings = lint_paths(
        [Path(p) for p in paths_to_check], ruleset, exclude=exclude, project_root=root
    )
    return summarise(findings)


@mcp.tool(
    description=(
        "Get the writing rules as instructions, ready to follow. Use this before "
        "writing prose, documentation, comments, or a commit message."
    )
)
def get_style_rules(
    style: Annotated[
        str, "minimal for the absolutes only, compact for every rule, full to add examples."
    ] = "compact",
    packs: Annotated[list[str], "Limit to these rule packs. Optional."] = [],  # noqa: B006
    project_dir: Annotated[str, "Absolute path of the project. Optional."] = "",
) -> str:
    """The rendered rules, as Markdown."""
    if style not in STYLES:
        raise ValueError(f"style must be one of: {', '.join(STYLES)}")

    ruleset, config, root = load_rules(project_dir or None)
    if packs:
        ruleset = resolve_ruleset(config.merged_with(Config(packs=tuple(packs))), project_root=root)
    return render_body(ruleset, style=style)


@mcp.tool(
    description=(
        "Explain one rule: what it says, why it exists, and a wrong/right example. "
        "Also returns the rule as TOML, ready to paste into debabble.toml and edit."
    )
)
def explain_rule(
    rule_id: Annotated[str, "The rule id, for example vocabulary.hype-verbs."],
    project_dir: Annotated[str, "Absolute path of the project. Optional."] = "",
) -> dict[str, Any]:
    """Everything known about one rule."""
    ruleset, _config, _root = load_rules(project_dir or None)
    rule = ruleset.rule(rule_id)
    if rule is None:
        known = sorted(r.id for r in ruleset.rules)
        raise ValueError(f"No rule {rule_id!r}. Known rules: {', '.join(known[:40])}")

    return {
        "id": rule.id,
        "title": rule.display_title,
        "severity": str(rule.severity),
        "instruction": rule.instruction,
        "why": rule.why,
        "wrong": rule.wrong,
        "right": rule.right,
        "terms": list(rule.terms),
        "registers": list(rule.registers),
        "toml": rule_to_toml(rule),
    }


@mcp.tool(description="List the rule packs and the rules in each, with their severities.")
def list_rules(
    pack: Annotated[str, "Limit to one pack. Optional."] = "",
    project_dir: Annotated[str, "Absolute path of the project. Optional."] = "",
) -> dict[str, Any]:
    """A summary of what is in effect."""
    ruleset, config, _root = load_rules(project_dir or None)
    packs = [p for p in ruleset.packs if not pack or p.id == pack]
    return {
        "style": config.effective_style,
        "packs": [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "rules": [
                    {
                        "id": r.id,
                        "title": r.display_title,
                        "severity": str(r.severity),
                        "instruction": r.instruction,
                    }
                    for r in p.rules
                ],
            }
            for p in packs
        ],
    }


# A prompt and a resource


@mcp.prompt(description="Rewrite text so it follows the debabble rules.")
def rewrite(text: Annotated[str, "The text to rewrite."]) -> str:
    ruleset, _config, _root = load_rules()
    return render_rewrite_command(ruleset).replace("$ARGUMENTS", text)


@mcp.resource("debabble://styleguide", description="The full writing rules, as Markdown.")
def styleguide() -> str:
    ruleset, config, _root = load_rules()
    return render_body(ruleset, style=config.effective_style)


def main() -> None:
    """Entry point for the ``debabble-mcp`` script."""
    try:
        # stdout carries the protocol, so nothing else may be written to it.
        mcp.run()
    except DebabbleError as err:
        print(f"debabble: {err}", file=sys.stderr)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
