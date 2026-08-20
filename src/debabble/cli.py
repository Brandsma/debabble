"""The debabble command line.

Run ``debabble`` with no arguments for a summary of what is installed here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from . import install, paths
from .config import STYLES, Config, known_ids, load_config, resolve_ruleset
from .errors import ConfigError, DebabbleError
from .models import REGISTERS, Severity
from .packs import load_all_packs, rule_to_toml
from .render import render_body, render_rewrite_command
from .targets import CONTENT_REWRITE, all_targets, get_target

console = Console()
# soft_wrap keeps Rich from breaking a long file path across lines, which
# makes the path in an error message impossible to copy.
err_console = Console(stderr=True, soft_wrap=True)

app = App(
    name="debabble",
    help="Install no-AI-speak writing rules into your AI coding tools.",
    version="0.1.0",
)

# Shared option types, so every command spells them the same way.
GlobalFlag = Annotated[
    bool,
    Parameter(
        name=["--global", "-g"],
        help="Act on your user-wide setup instead of this project.",
    ),
]
TargetOption = Annotated[
    tuple[str, ...],
    Parameter(
        name=["--target", "-t"],
        help="Tools to write to. Repeatable. Defaults to your configured targets.",
        consume_multiple=True,
    ),
]
PackOption = Annotated[
    tuple[str, ...],
    Parameter(
        name=["--pack", "-p"],
        help="Rule packs to include. Repeatable. Defaults to your configured packs.",
        consume_multiple=True,
    ),
]
StyleOption = Annotated[
    str,
    Parameter(name=["--style", "-s"], help="'compact' states the rules; 'full' adds examples."),
]
SeverityOption = Annotated[
    tuple[str, ...],
    Parameter(
        name=["--severity"],
        help="Change a rule or pack: --severity vocabulary.intensity-cluster=off. Repeatable.",
        consume_multiple=True,
    ),
]
AvoidOption = Annotated[
    tuple[str, ...],
    Parameter(
        name=["--avoid"],
        help="Extra words to ban for this run. Repeatable.",
        consume_multiple=True,
    ),
]
DryRunFlag = Annotated[
    bool, Parameter(name=["--dry-run", "-n"], help="Show what would change; write nothing.")
]

_SEVERITY_STYLES = {
    Severity.BAN: "red",
    Severity.FLAG: "yellow",
    Severity.OFF: "dim",
}

_ACTION_STYLES = {
    install.CREATE: ("green", "created"),
    install.UPDATE: ("yellow", "updated"),
    install.UNCHANGED: ("dim", "unchanged"),
    install.DELETE: ("red", "deleted"),
    install.STRIP: ("red", "block removed"),
    install.SKIP: ("dim", "skipped"),
    install.MISSING: ("dim", "missing"),
    install.DRIFT: ("magenta", "edited by hand"),
}


# Shared plumbing


def _parse_severity_flags(values: tuple[str, ...]) -> dict[str, Severity]:
    parsed: dict[str, Severity] = {}
    for value in values:
        key, sep, level = value.partition("=")
        if not sep:
            raise ConfigError(
                f"--severity expects ID=LEVEL, for example --severity vocabulary=flag "
                f"(got {value!r})."
            )
        parsed[key.strip()] = Severity.parse(level.strip(), where="--severity")
    return parsed


def _known_ids(project_root: Path | None) -> set[str]:
    """Every pack and rule id that exists, whether or not it is switched on."""
    return known_ids(load_all_packs(paths.custom_pack_dirs(project_root)))


def _scope_and_root(is_global: bool) -> tuple[str, Path | None]:
    if is_global:
        return "global", None
    return "project", paths.find_project_root()


def _prepare(
    *,
    is_global: bool,
    targets: tuple[str, ...] = (),
    packs: tuple[str, ...] = (),
    style: str = "",
    severity: tuple[str, ...] = (),
    avoid: tuple[str, ...] = (),
):
    """Load configuration, fold in command line overrides, and resolve the rules."""
    scope, project_root = _scope_and_root(is_global)
    config = load_config(project_root, scope=scope)

    overrides = Config(
        packs=tuple(packs) if packs else None,
        targets=tuple(targets),
        style=style,
        severity=_parse_severity_flags(severity),
        avoid=tuple(avoid),
    )
    config = config.merged_with(overrides)

    if config.style and config.style not in STYLES:
        raise ConfigError(f"--style must be one of: {', '.join(STYLES)}.")

    ruleset = resolve_ruleset(config, project_root=project_root)
    return scope, project_root, config, ruleset


def _print_changes(outcome: install.Outcome, project_root: Path | None) -> None:
    if not outcome.changes:
        console.print("[dim]Nothing to do.[/dim]")
    for change in outcome.changes:
        colour, label = _ACTION_STYLES.get(change.action, ("white", change.action))
        location = paths.display(change.path, relative_to=project_root) if str(change.path) else ""
        line = Text()
        line.append(f"  {label:<14}", style=colour)
        line.append(location)
        if change.detail:
            line.append(f"  {change.detail}", style="dim")
        console.print(line)

    for warning in outcome.warnings:
        console.print("[yellow]note[/yellow]", escape(warning))

    if outcome.dry_run:
        console.print("\n[dim]Nothing was written. Drop --dry-run to apply.[/dim]")


def _summarise_rules(ruleset, config: Config) -> None:
    """One line describing the rule set, including what it costs to carry."""
    counts = ruleset.counts()
    active = len(ruleset.active_rules)
    style = config.effective_style
    size = len(render_body(ruleset, style=style))
    console.print(
        f"[bold]{active}[/bold] rules active "
        f"([red]{counts[Severity.BAN]} ban[/red], [yellow]{counts[Severity.FLAG]} flag[/yellow], "
        f"[dim]{counts[Severity.OFF]} off[/dim]) "
        f"from {len(ruleset.packs)} packs"
    )
    # Instruction files are read on every request, so the size is worth showing.
    hint = ""
    if size > 15000 and style != "minimal":
        hint = " — for less, try --style minimal or fewer packs"
    console.print(
        f"[dim]style {style}, about {size // 1000} kB "
        f"(~{size // 4000}k tokens) in every session{hint}[/dim]"
    )


# Commands


@app.command
def apply(
    *,
    target: TargetOption = (),
    pack: PackOption = (),
    style: StyleOption = "",
    severity: SeverityOption = (),
    avoid: AvoidOption = (),
    save: Annotated[
        bool, Parameter(help="Write the options used into your config so they stick.")
    ] = False,
    is_global: GlobalFlag = False,
    dry_run: DryRunFlag = False,
) -> None:
    """Write the rules into your AI coding tools.

    Re-running this is safe: unchanged settings change nothing on disk. Naming
    targets explicitly refreshes only those, and never uninstalls anything.
    Add --save to keep the options you passed.
    """
    scope, project_root, config, ruleset = _prepare(
        is_global=is_global,
        targets=target,
        packs=pack,
        style=style,
        severity=severity,
        avoid=avoid,
    )

    where = "globally" if scope == "global" else f"in {paths.display(project_root)}"
    console.print(f"Applying {where}")
    _summarise_rules(ruleset, config)
    console.print()

    outcome = install.apply(
        ruleset,
        config,
        scope=scope,
        project_root=project_root,
        target_ids=tuple(target) if target else None,
        dry_run=dry_run,
    )
    _print_changes(outcome, project_root)

    for warning in install.shadowing_warnings(
        project_root if scope == "project" else None,
        tuple(config.effective_targets),
    ):
        console.print("[yellow]note[/yellow]", escape(warning))

    if save and not dry_run:
        _save_profile(scope, project_root, config, targets=target, packs=pack, style=style)
    elif target and not dry_run:
        # A one-off --target is not remembered, and a later plain `apply`
        # reconciles against the config and would take it back out again.
        on_disk = load_config(project_root, scope=scope)
        unsaved = [t for t in target if t not in on_disk.effective_targets]
        if unsaved:
            console.print(
                f"\n[yellow]note[/yellow] {', '.join(unsaved)} "
                "is not in your config, so a later plain `debabble apply` will remove it. "
                "Re-run with --save to keep it."
            )


def _save_profile(
    scope: str,
    project_root: Path | None,
    config: Config,
    *,
    targets: tuple[str, ...],
    packs: tuple[str, ...],
    style: str,
) -> None:
    """Persist the options used on this run into the config file.

    New targets are added to what the file already asks for rather than
    replacing it, so saving one target does not quietly drop the others.
    """
    path = _config_path(scope, project_root)
    # `config` has already been merged with the command line, so the file's own
    # targets have to be read again to add to them rather than overwrite them.
    on_disk = load_config(project_root, scope=scope)

    def mutate(document) -> None:
        import tomlkit

        if "profile" not in document:
            document["profile"] = tomlkit.table()
        profile = document["profile"]
        if targets:
            profile["targets"] = list(dict.fromkeys(on_disk.targets + targets))
        if packs:
            profile["packs"] = list(packs)
        if style:
            profile["style"] = style

    _edit_config(path, mutate)
    console.print(f"\nSaved to {paths.display(path, relative_to=project_root)}.")


@app.command
def remove(
    *,
    target: TargetOption = (),
    is_global: GlobalFlag = False,
    dry_run: DryRunFlag = False,
) -> None:
    """Uninstall the rules.

    Files debabble created are deleted; files it only added a block to are
    edited back, restoring a backup when one was taken.
    """
    scope, project_root = _scope_and_root(is_global)
    outcome = install.remove(
        scope=scope,
        project_root=project_root,
        target_ids=tuple(target) if target else None,
        dry_run=dry_run,
    )
    _print_changes(outcome, project_root)


@app.command
def status(*, is_global: GlobalFlag = False) -> None:
    """Show what is installed here, and whether it is current."""
    scope, project_root, config, ruleset = _prepare(is_global=is_global)
    _current, entries = install.status(ruleset, config, scope=scope, project_root=project_root)

    where = "Global" if scope == "global" else f"Project {paths.display(project_root)}"
    console.print(f"[bold]{where}[/bold]")

    if config.sources:
        for source in config.sources:
            console.print(f"[dim]config: {paths.display(source, relative_to=project_root)}[/dim]")
    else:
        console.print("[dim]config: none found, using defaults[/dim]")

    _summarise_rules(ruleset, config)
    console.print()

    if not entries:
        console.print("Nothing installed yet. Run [bold]debabble apply[/bold].")
        return

    table = Table(box=None, pad_edge=False)
    table.add_column("tool", style="bold")
    table.add_column("state")
    table.add_column("file", style="dim", overflow="fold")
    for entry in entries:
        colour, label = _ACTION_STYLES.get(entry.state, ("white", entry.state))
        detail = f" [dim]{entry.detail}[/dim]" if entry.detail else ""
        table.add_row(
            entry.target,
            f"[{colour}]{label}[/{colour}]{detail}",
            paths.display(entry.path, relative_to=project_root),
        )
    console.print(table)

    if any(e.state == install.UPDATE for e in entries):
        console.print(
            "\n[yellow]Some files are out of date. Run [bold]debabble apply[/bold].[/yellow]"
        )

    for warning in install.shadowing_warnings(
        project_root if scope == "project" else None,
        tuple(config.effective_targets),
    ):
        console.print("[yellow]note[/yellow]", escape(warning))


@app.command(name="render")
def render_cmd(
    *,
    target: Annotated[
        str,
        Parameter(name=["--target", "-t"], help="Render exactly as this tool would receive it."),
    ] = "",
    pack: PackOption = (),
    style: StyleOption = "",
    severity: SeverityOption = (),
    is_global: GlobalFlag = False,
) -> None:
    """Print the rules to standard output without writing anything.

    Useful for tools that keep their rules in application settings rather than a
    file, such as Cursor's user rules: render, then paste.
    """
    scope, project_root, config, ruleset = _prepare(
        is_global=is_global, packs=pack, style=style, severity=severity
    )

    if not target:
        sys.stdout.write(render_body(ruleset, style=config.effective_style))
        return

    resolved = get_target(target)
    files = resolved.files(scope, project_root or Path.cwd())
    if not files:
        note = resolved.note(scope)
        if note:
            err_console.print(f"[yellow]{note}[/yellow]")
        sys.stdout.write(render_body(ruleset, style=config.effective_style))
        return

    for target_file in files:
        if target_file.content == CONTENT_REWRITE:
            sys.stdout.write(render_rewrite_command(ruleset, style=config.effective_style))
        else:
            body, _ = install.build_content(target_file, ruleset, config.effective_style)
            sys.stdout.write(body)


@app.command(name="lint")
def lint_cmd(
    paths: Annotated[
        tuple[Path, ...],
        Parameter(help="Files or directories to check. Defaults to the current directory."),
    ] = (),
    *,
    register: Annotated[
        str,
        Parameter(
            name=["--register", "-r"],
            help="Force a register: prose, docs, comments, commits, or code.",
        ),
    ] = "",
    output: Annotated[str, Parameter(name=["--format", "-f"], help="text or json.")] = "text",
    strict: Annotated[
        bool, Parameter(help="Fail on flagged rules too, not only banned ones.")
    ] = False,
    is_global: GlobalFlag = False,
) -> None:
    """Check files against the rules, and report what matched.

    Exits non-zero when a banned rule matched, so this works as a CI gate. Rules
    a regex cannot judge are skipped rather than guessed at, and code inside
    fences is not read as prose.
    """
    from . import lint as lint_engine

    scope, project_root, config, ruleset = _prepare(is_global=is_global)
    targets_to_check = list(paths) or [Path.cwd()]
    exclude = install.lint_excludes(config, scope=scope, project_root=project_root)

    missing = [p for p in targets_to_check if not p.exists()]
    if missing:
        raise ConfigError("No such file or directory: " + ", ".join(str(p) for p in missing) + ".")

    if register:
        if register not in REGISTERS:
            raise ConfigError(f"--register must be one of: {', '.join(REGISTERS)}.")
        # Forcing a register still has to walk directories, or naming one
        # would quietly check nothing at all.
        files: list[Path] = []
        for path in targets_to_check:
            if path.is_dir():
                files += lint_engine.walk_files(path, exclude, project_root=project_root)
            else:
                files.append(path)

        findings = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            findings += lint_engine.lint_text(text, ruleset, register=register, path=path)
    else:
        findings = lint_engine.lint_paths(
            targets_to_check, ruleset, exclude=exclude, project_root=project_root
        )

    if output == "json":
        import json

        sys.stdout.write(json.dumps([f.as_dict() for f in findings], indent=2) + "\n")
    else:
        _print_findings(findings, config)

    worst = lint_engine.worst_severity(findings)
    if worst is Severity.BAN or (strict and worst is not None):
        raise SystemExit(1)


def _print_findings(findings: list, config: Config) -> None:
    if not findings:
        console.print("[green]No findings.[/green]")
        return

    root = paths.find_project_root()
    for finding in findings:
        colour = _SEVERITY_STYLES[finding.severity]
        where = (
            f"{paths.display(finding.path, relative_to=root)}:{finding.line}:{finding.column}"
            if finding.path
            else f"{finding.line}:{finding.column}"
        )
        console.print(
            f"[dim]{where}[/dim] [{colour}]{finding.severity}[/{colour}] "
            f"{finding.rule_id}  [bold]{finding.matched}[/bold]"
        )
        console.print(f"    [dim]{finding.message}[/dim]")

    bans = sum(1 for f in findings if f.severity is Severity.BAN)
    flags = len(findings) - bans
    console.print(
        f"\n[bold]{len(findings)}[/bold] findings "
        f"([red]{bans} banned[/red], [yellow]{flags} flagged[/yellow])"
    )


@app.command
def packs(*, is_global: GlobalFlag = False) -> None:
    """List the rule packs and whether they are switched on."""
    _, project_root, _config, ruleset = _prepare(is_global=is_global)
    enabled = {p.id for p in ruleset.packs}

    custom_dirs = paths.custom_pack_dirs(project_root)

    table = Table(box=None, pad_edge=False)
    table.add_column("pack", style="bold")
    table.add_column("on")
    table.add_column("rules", justify="right")
    table.add_column("what it covers", overflow="fold")

    for pack_obj in sorted(load_all_packs(custom_dirs), key=lambda p: (-p.priority, p.id)):
        live = ruleset.pack(pack_obj.id)
        active = len(live.active_rules) if live else 0
        on = "[green]yes[/green]" if pack_obj.id in enabled else "[dim]no[/dim]"
        count = f"{active}/{len(pack_obj.rules)}" if live else str(len(pack_obj.rules))
        table.add_row(pack_obj.id, on, count, pack_obj.description)

    console.print(table)
    console.print(
        "\n[dim]Switch packs on or off with the profile.packs list in debabble.toml, "
        "or per run with --pack.[/dim]"
    )


@app.command
def rules(
    query: Annotated[str, Parameter(help="Show one rule by id, or search for text.")] = "",
    *,
    pack: PackOption = (),
    show_off: Annotated[
        bool, Parameter(name="--all", help="Include rules that are switched off.")
    ] = False,
    is_global: GlobalFlag = False,
) -> None:
    """List the rules in effect, or show one rule in full.

    ``debabble rules vocabulary.tier1`` prints that rule as TOML you can paste
    into debabble.toml and edit.
    """
    *_, ruleset = _prepare(is_global=is_global, packs=pack)

    exact = ruleset.rule(query) if query else None
    if exact is not None:
        _show_rule(exact)
        return

    matches = [
        r
        for r in ruleset.rules
        if (show_off or r.severity.is_active)
        and (
            not query
            or query.lower() in r.id.lower()
            or query.lower() in r.instruction.lower()
            or query.lower() in r.display_title.lower()
        )
    ]
    if not matches:
        console.print(f"No rules match {query!r}.")
        return

    table = Table(box=None, pad_edge=False)
    table.add_column("rule", style="bold")
    table.add_column("severity")
    table.add_column("what it says", overflow="fold")
    for rule in matches:
        colour = _SEVERITY_STYLES[rule.severity]
        table.add_row(rule.id, f"[{colour}]{rule.severity}[/{colour}]", rule.instruction)
    console.print(table)
    console.print(
        f"\n[dim]{len(matches)} rules. "
        "Show one in full with `debabble rules <id>`; change one with "
        "`debabble severity <id> <level>`.[/dim]"
    )


def _show_rule(rule) -> None:
    console.print(f"[bold]{rule.id}[/bold] — {rule.display_title}")
    if rule.why:
        console.print(f"[dim]{rule.why}[/dim]")
    if rule.wrong and rule.right:
        console.print(f"\n  [red]no[/red]  {rule.wrong}")
        console.print(f"  [green]yes[/green] {rule.right}")

    console.print("\n[dim]Paste this into debabble.toml to change it:[/dim]")
    # Straight to stdout: Rich would read [[rules]] as markup and wrap long
    # lines, and this text has to survive being copied verbatim.
    sys.stdout.write(rule_to_toml(rule) + "\n")


@app.command
def severity(
    rule_id: Annotated[str, Parameter(help="A rule id, or a whole pack id.")],
    level: Annotated[str, Parameter(help="ban, flag, or off.")],
    *,
    is_global: GlobalFlag = False,
) -> None:
    """Change how hard a rule or a whole pack pushes, and save it.

    ``debabble severity vocabulary flag`` softens every vocabulary rule;
    ``debabble severity phrases.closers off`` switches one rule off.
    """
    parsed = Severity.parse(level, where="severity")
    scope, project_root = _scope_and_root(is_global)

    # Check against every pack that exists, not only the ones switched on, so a
    # severity can be set for a pack before it is enabled.
    if rule_id not in _known_ids(project_root):
        raise ConfigError(
            f"No rule or pack called {rule_id!r}. "
            "Run `debabble rules` to list rules, or `debabble packs` to list packs."
        )

    path = _config_path(scope, project_root)
    _edit_config(path, lambda doc: _set_severity(doc, rule_id, parsed.value))
    console.print(
        f"Set [bold]{rule_id}[/bold] to [bold]{parsed}[/bold] "
        f"in {paths.display(path, relative_to=project_root)}."
    )

    # Setting a severity on a pack nobody enabled changes nothing you can see.
    *_, ruleset = _prepare(is_global=is_global)
    # Name the pack that would have to be switched on, whether the user gave a
    # pack id, a full rule id, or a rule's short id.
    if (
        ruleset.pack(rule_id) is not None
        or ruleset.rule(rule_id) is not None
        or any(r.short_id == rule_id for r in ruleset.rules)
    ):
        pack_id = None
    else:
        pack_id = rule_id.split(".", 1)[0]

    if pack_id is not None:
        console.print(
            f"[yellow]note[/yellow] {pack_id} is not one of your packs, so this has no "
            f"effect yet. Turn it on with: debabble apply --pack {pack_id} --save"
        )
    console.print("[dim]Run `debabble apply` to update your tools.[/dim]")


@app.command
def avoid(
    words: Annotated[tuple[str, ...], Parameter(help="Words or phrases to ban.")],
    *,
    is_global: GlobalFlag = False,
) -> None:
    """Ban a word or phrase of your own.

    ``debabble avoid supercharge`` adds it to your config; run apply to push it
    out to your tools.
    """
    if not words:
        raise ConfigError("Give at least one word, for example: debabble avoid supercharge")

    scope, project_root = _scope_and_root(is_global)
    path = _config_path(scope, project_root)
    _edit_config(path, lambda doc: _add_avoid(doc, words))
    listed = ", ".join(words)
    console.print(f"Now avoiding: [bold]{listed}[/bold]")
    console.print(
        f"[dim]Saved to {paths.display(path, relative_to=project_root)}. "
        "Run `debabble apply` to update your tools.[/dim]"
    )


@app.command
def targets(*, is_global: GlobalFlag = False) -> None:
    """List the tools debabble can write to."""
    scope, project_root = _scope_and_root(is_global)
    root = project_root or Path.cwd()

    table = Table(box=None, pad_edge=False)
    table.add_column("target", style="bold")
    table.add_column("where it writes", overflow="fold")
    table.add_column("how", style="dim")

    for target in all_targets():
        files = target.files(scope, root)
        if files:
            where = "\n".join(paths.display(f.path, relative_to=project_root) for f in files)
            how = ", ".join(dict.fromkeys("own file" if f.owns_file else "block" for f in files))
        else:
            where = f"[dim]{target.note(scope) or 'not available in this scope'}[/dim]"
            how = ""
        table.add_row(target.id, where, how)

    console.print(f"[bold]{'Global' if scope == 'global' else 'Project'} paths[/bold]\n")
    console.print(table)


@app.command
def init(*, is_global: GlobalFlag = False, force: bool = False) -> None:
    """Write a starter debabble.toml you can edit."""
    scope, project_root = _scope_and_root(is_global)
    path = _config_path(scope, project_root)

    if path.exists() and not force:
        console.print(
            f"{paths.display(path, relative_to=project_root)} already exists. "
            "Pass --force to overwrite it."
        )
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_starter_config(), encoding="utf-8")
    console.print(f"Wrote {paths.display(path, relative_to=project_root)}")
    console.print("[dim]Edit it, then run `debabble apply`.[/dim]")


@app.default
def overview(
    unknown: Annotated[
        tuple[str, ...], Parameter(show=False, help="Anything that is not a command.")
    ] = (),
) -> None:
    """Show what is installed here and what to do next."""
    if unknown:
        # Without this, a typo reports "Unused Tokens", which tells the reader
        # nothing about what they should have typed.
        import difflib

        commands = sorted(name for name in app if not name.startswith("-"))
        close = difflib.get_close_matches(unknown[0], commands, n=1)
        hint = f" Did you mean 'debabble {close[0]}'?" if close else ""
        raise ConfigError(
            f"There is no '{unknown[0]}' command.{hint} The commands are: {', '.join(commands)}."
        )
    status(is_global=False)


# Config editing (comment preserving)


def _config_path(scope: str, project_root: Path | None) -> Path:
    if scope == "global" or project_root is None:
        return paths.global_config_file()
    return paths.project_config_file(project_root)


def _edit_config(path: Path, mutate) -> None:
    """Apply a change to a config file without losing its comments or layout."""
    import tomlkit

    if path.is_file():
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        document = tomlkit.parse(_starter_config())
    mutate(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(document), encoding="utf-8")


def _set_severity(document, rule_id: str, level: str) -> None:
    import tomlkit

    if "severity" not in document:
        document["severity"] = tomlkit.table()
    document["severity"][rule_id] = level


def _add_avoid(document, words: tuple[str, ...]) -> None:
    import tomlkit

    if "custom" not in document:
        document["custom"] = tomlkit.table()
    custom = document["custom"]
    existing = list(custom.get("avoid", []))
    for word in words:
        if word not in existing:
            existing.append(word)
    custom["avoid"] = existing


_STARTER_TEMPLATE = """# debabble configuration.
# Commit this file: it is the whole story of what your tools receive.

[profile]
# Packs to enable. Run `debabble packs` to see them all.
{packs}

# Tools to write to. Run `debabble targets` to see where each one writes.
targets = ["claude-code"]

# "minimal" is the absolutes only, "compact" states every rule, "full" adds a
# wrong/right example to each.
style = "compact"

# Change how hard any rule or whole pack pushes: ban, flag, or off.
# `debabble severity <id> <level>` edits this section for you.
[severity]
# "vocabulary.intensity-cluster" = "off"
# "corporate-speak" = "ban"

[custom]
# Your own banned words. `debabble avoid <word>` adds to this list.
avoid = []

# Words a shipped rule bans that you want to keep using.
allow = []

# Edit any shipped rule by id, or define a new one. `debabble rules <id>`
# prints a rule in exactly this format, ready to paste and change.
# [[rules]]
# id = "vocabulary.hype-verbs"
# severity = "flag"
"""


def _starter_config() -> str:
    """The starter file, with the pack list taken from the packs themselves.

    Writing the nine names by hand meant a new default pack silently missed
    everyone who had already run `debabble init`.
    """
    from .packs import load_builtin_packs

    names = [p.id for p in load_builtin_packs() if p.default]
    listed = [f'    "{name}",' for name in names]
    return _STARTER_TEMPLATE.format(packs="\n".join(["packs = [", *listed, "]"]))


def main() -> None:
    """Entry point. Turns expected errors into a message and a non-zero exit."""
    try:
        app()
    except DebabbleError as err:
        # Escape the message: it routinely names TOML sections like [profile],
        # and Rich would read those as markup and print nothing in their place.
        err_console.print("[red]error[/red]", escape(str(err)))
        raise SystemExit(1) from err
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
