"""Configuration: reading debabble.toml and turning packs into the rules in effect.

Customisation happens at three levels, from quickest to most thorough:

1. ``[custom] avoid = ["supercharge"]`` — ban a word in one line.
2. ``[severity]`` — change how hard any rule or whole pack pushes, including
   turning it ``off``. The same knob exists on the command line as
   ``--severity ID=LEVEL``.
3. ``[[rules]]`` — override any field of any shipped rule by id, or define a
   brand new rule. The field names are identical to the ones in the shipped
   pack files, so ``debabble rules show ID`` prints something you can paste
   straight into your config and edit.
"""

from __future__ import annotations

import difflib
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import paths
from .errors import ConfigError
from .models import Pack, Rule, RuleSet, Severity
from .packs import build_rule, load_all_packs

STYLES = ("minimal", "compact", "full")
DEFAULT_STYLE = "compact"
DEFAULT_TARGETS = ("claude-code",)

_CONFIG_SECTIONS = {"profile", "severity", "custom", "rules", "lint"}
_LINT_KEYS = {"exclude"}
_PROFILE_KEYS = {"packs", "targets", "style"}
_CUSTOM_KEYS = {"avoid", "allow"}


@dataclass(frozen=True, slots=True)
class Config:
    """Everything a user can say about how debabble should behave."""

    # None means "use each pack's own default", which is how a fresh install behaves.
    packs: tuple[str, ...] | None = None
    targets: tuple[str, ...] = ()
    style: str = ""
    severity: dict[str, Severity] = field(default_factory=dict)
    avoid: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    rule_overrides: tuple[dict[str, Any], ...] = ()
    # Paths `debabble lint` should not read, as globs relative to the project
    # root. Data files and quoted research are the usual cases.
    exclude: tuple[str, ...] = ()
    sources: tuple[Path, ...] = ()

    def merged_with(self, other: Config) -> Config:
        """Combine two configs, with ``other`` winning on anything it sets.

        List-valued settings replace rather than union, so a project config is a
        complete statement of what that project wants. Severity maps and word
        lists do merge, because they are additive by nature.
        """
        return Config(
            packs=other.packs if other.packs is not None else self.packs,
            targets=other.targets or self.targets,
            style=other.style or self.style,
            severity={**self.severity, **other.severity},
            avoid=tuple(dict.fromkeys(self.avoid + other.avoid)),
            allow=tuple(dict.fromkeys(self.allow + other.allow)),
            rule_overrides=self.rule_overrides + other.rule_overrides,
            exclude=tuple(dict.fromkeys(self.exclude + other.exclude)),
            sources=self.sources + other.sources,
        )

    @property
    def effective_style(self) -> str:
        return self.style or DEFAULT_STYLE

    @property
    def effective_targets(self) -> tuple[str, ...]:
        return self.targets or DEFAULT_TARGETS


def _as_str_tuple(value: object, *, where: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    raise ConfigError(f"{where}: expected a list of strings, got {type(value).__name__}.")


def parse_config(data: dict[str, Any], *, source: Path | None = None) -> Config:
    """Turn parsed TOML into a :class:`Config`, with errors that name the file."""
    where = str(source) if source else "config"

    unknown = set(data) - _CONFIG_SECTIONS
    if unknown:
        raise ConfigError(
            f"{where}: unknown section [{min(unknown)}]. "
            f"Valid sections are: {', '.join(sorted(_CONFIG_SECTIONS))}."
        )

    profile = data.get("profile", {})
    if not isinstance(profile, dict):
        raise ConfigError(f"{where}: [profile] must be a table.")
    unknown = set(profile) - _PROFILE_KEYS
    if unknown:
        raise ConfigError(
            f"{where}: unknown key {min(unknown)!r} in [profile]. "
            f"Valid keys are: {', '.join(sorted(_PROFILE_KEYS))}."
        )

    packs = None
    if "packs" in profile:
        packs = _as_str_tuple(profile["packs"], where=f"{where}: profile.packs")

    targets = ()
    if "targets" in profile:
        targets = _as_str_tuple(profile["targets"], where=f"{where}: profile.targets")

    style = ""
    if "style" in profile:
        style = str(profile["style"])
        if style not in STYLES:
            raise ConfigError(
                f"{where}: profile.style is {style!r}; use one of: {', '.join(STYLES)}."
            )

    severity_raw = data.get("severity", {})
    if not isinstance(severity_raw, dict):
        raise ConfigError(f"{where}: [severity] must be a table of 'rule-or-pack-id = level'.")
    severity = {
        str(key): Severity.parse(value, where=f"{where}: severity.{key}")
        for key, value in severity_raw.items()
    }

    custom = data.get("custom", {})
    if not isinstance(custom, dict):
        raise ConfigError(f"{where}: [custom] must be a table.")
    unknown = set(custom) - _CUSTOM_KEYS
    if unknown:
        raise ConfigError(
            f"{where}: unknown key {min(unknown)!r} in [custom]. "
            f"Valid keys are: {', '.join(sorted(_CUSTOM_KEYS))}."
        )
    avoid = _as_str_tuple(custom.get("avoid", []), where=f"{where}: custom.avoid")
    allow = _as_str_tuple(custom.get("allow", []), where=f"{where}: custom.allow")

    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise ConfigError(f"{where}: 'rules' must be a list of [[rules]] tables.")
    for entry in rules:
        if not isinstance(entry, dict) or not str(entry.get("id", "")).strip():
            raise ConfigError(f"{where}: every [[rules]] entry needs an 'id'.")

    lint_section = data.get("lint", {})
    if not isinstance(lint_section, dict):
        raise ConfigError(f"{where}: [lint] must be a table.")
    unknown = set(lint_section) - _LINT_KEYS
    if unknown:
        raise ConfigError(
            f"{where}: unknown key {min(unknown)!r} in [lint]. "
            f"Valid keys are: {', '.join(sorted(_LINT_KEYS))}."
        )
    exclude = _as_str_tuple(lint_section.get("exclude", []), where=f"{where}: lint.exclude")

    return Config(
        packs=packs,
        targets=targets,
        style=style,
        severity=severity,
        avoid=avoid,
        allow=allow,
        rule_overrides=tuple(rules),
        exclude=exclude,
        sources=(source,) if source else (),
    )


def load_config_file(path: Path) -> Config:
    """Read one config file. A missing file is an empty config, not an error."""
    if not path.is_file():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path}: not valid TOML — {err}") from err
    except OSError as err:
        raise ConfigError(f"{path}: could not be read — {err}") from err
    return parse_config(data, source=path)


def load_config(project_root: Path | None, *, scope: str = "project") -> Config:
    """Load the config in effect for a scope.

    A project that has its own ``debabble.toml`` is self-contained: the global
    config is ignored, so the files debabble writes are a pure function of the
    committed config and every teammate gets identical output. A project with no
    config of its own falls back to the global one, which is what makes
    ``debabble apply --global`` useful as a personal default.
    """
    global_config = load_config_file(paths.global_config_file())
    if scope == "global" or project_root is None:
        return global_config

    project_file = paths.project_config_file(project_root)
    if project_file.is_file():
        return load_config_file(project_file)
    return global_config


# --------------------------------------------------------------------------
# Turning configuration into the rules that are actually in effect
# --------------------------------------------------------------------------


def _severity_for(rule: Rule, severity_map: dict[str, Severity]) -> Severity:
    """Rule-specific settings win over pack-wide ones."""
    if rule.id in severity_map:
        return severity_map[rule.id]
    if rule.short_id in severity_map:
        return severity_map[rule.short_id]
    if rule.pack in severity_map:
        return severity_map[rule.pack]
    return rule.severity


def _apply_allow(rule: Rule, allow: frozenset[str]) -> Rule:
    """Drop allow-listed terms from a rule's word and phrase lists."""
    if not allow or not rule.terms:
        return rule
    words = tuple(w for w in rule.words if w.lower() not in allow)
    phrases = tuple(p for p in rule.phrases if p.lower() not in allow)
    if words == rule.words and phrases == rule.phrases:
        return rule
    # A list emptied by allow-listing has nothing left to say.
    if rule.kind in ("wordlist", "phrase") and not (words or phrases):
        return replace(rule, words=words, phrases=phrases, severity=Severity.OFF)
    return replace(rule, words=words, phrases=phrases)


def _custom_pack(avoid: tuple[str, ...], overrides: list[dict[str, Any]]) -> Pack | None:
    """Build the pack that holds a user's own words and brand new rules."""
    rules: list[Rule] = []
    if avoid:
        rules.append(
            Rule(
                id="custom.avoid",
                title="Words you asked to avoid",
                instruction=("Never use these words or phrases: " + ", ".join(sorted(avoid)) + "."),
                severity=Severity.BAN,
                kind="wordlist",
                registers=("prose", "docs", "comments", "commits"),
                words=tuple(avoid),
                why="Added with `debabble avoid` or the [custom] avoid list.",
            )
        )
    for entry in overrides:
        rules.append(build_rule(entry, pack_id="custom", where="debabble.toml"))
    if not rules:
        return None
    return Pack(
        id="custom",
        title="Your rules",
        description="Rules you added yourself.",
        rules=tuple(rules),
        priority=95,
        source="your config",
    )


def resolve_ruleset(config: Config, *, project_root: Path | None = None) -> RuleSet:
    """Apply a config to the available packs and return the rules in effect.

    The order is deliberate: field-level overrides first, then the severity map,
    so a quick ``[severity]`` entry always wins over a longer ``[[rules]]`` block
    that also set a severity.
    """
    custom_dirs = [paths.global_packs_dir()]
    if project_root is not None:
        custom_dirs.append(paths.project_packs_dir(project_root))

    available = {p.id: p for p in load_all_packs(custom_dirs)}

    # 1. Which packs are in play?
    if config.packs is None:
        selected_ids = [pid for pid, pack in available.items() if pack.default]
    else:
        selected_ids = []
        for pid in config.packs:
            if pid not in available:
                known = ", ".join(sorted(available))
                raise ConfigError(f"Unknown pack {pid!r}. Available packs: {known}.")
            selected_ids.append(pid)

    # 2. Split rule overrides into edits of shipped rules and brand new rules.
    known_rule_ids = {r.id for pid in available for r in available[pid].rules}
    edits: dict[str, dict[str, Any]] = {}
    additions: list[dict[str, Any]] = []
    for entry in config.rule_overrides:
        rule_id = str(entry["id"]).strip()
        if rule_id in known_rule_ids:
            edits[rule_id] = {**edits.get(rule_id, {}), **entry}
        elif "." in rule_id and rule_id.split(".", 1)[0] in available:
            pack_id = rule_id.split(".", 1)[0]
            known = ", ".join(sorted(r.short_id for r in available[pack_id].rules))
            raise ConfigError(
                f"No rule {rule_id!r} in pack {pack_id!r}. Rules in that pack: {known}."
            )
        else:
            additions.append(entry)

    # A severity set on an id that does not exist does nothing, silently. Say so:
    # a typo here is the difference between a rule being off and being on.
    known_ids = set(available) | {r.id for p in available.values() for r in p.rules}
    known_ids |= {r.short_id for p in available.values() for r in p.rules}
    for key in config.severity:
        if key not in known_ids:
            close = difflib.get_close_matches(key, sorted(known_ids), n=1)
            hint = f" Did you mean {close[0]!r}?" if close else ""
            raise ConfigError(
                f"[severity] names {key!r}, which is not a rule or pack.{hint} "
                "Run `debabble rules` or `debabble packs` to see what exists."
            )

    allow = frozenset(a.lower() for a in config.allow)

    # 3. Rebuild each selected pack with edits, allow-listing, and severities applied.
    resolved: list[Pack] = []
    for pid in selected_ids:
        pack = available[pid]
        rules: list[Rule] = []
        for rule in pack.rules:
            if rule.id in edits:
                merged = {**_rule_to_dict(rule), **edits[rule.id]}
                rule = build_rule(merged, pack_id=pid, where="debabble.toml")
            rule = _apply_allow(rule, allow)
            rule = rule.with_severity(_severity_for(rule, config.severity))
            rules.append(rule)
        resolved.append(replace(pack, rules=tuple(rules)))

    # 4. Add the user's own pack last so it is easy to spot in listings.
    custom = _custom_pack(config.avoid, additions)
    if custom is not None:
        custom = replace(
            custom,
            rules=tuple(r.with_severity(_severity_for(r, config.severity)) for r in custom.rules),
        )
        resolved.append(custom)

    return RuleSet(packs=tuple(resolved))


def _rule_to_dict(rule: Rule) -> dict[str, Any]:
    """A rule as plain TOML-shaped data, for merging and for `rules show`."""
    data: dict[str, Any] = {
        "id": rule.id,
        "instruction": rule.instruction,
        "severity": rule.severity.value,
        "kind": rule.kind,
        "registers": list(rule.registers),
        "channels": list(rule.channels),
    }
    if rule.title:
        data["title"] = rule.title
    if rule.scope != "any":
        data["scope"] = rule.scope
    for key in ("words", "phrases", "suggest"):
        value = getattr(rule, key)
        if value:
            data[key] = list(value)
    for key in ("pattern", "wrong", "right", "why", "fix", "replacement", "era"):
        value = getattr(rule, key)
        if value:
            data[key] = value
    if rule.max is not None:
        data["max"] = rule.max
        data["unit"] = rule.unit
        if rule.unit == "words":
            data["per_words"] = rule.per_words
    return data


__all__ = [
    "DEFAULT_STYLE",
    "DEFAULT_TARGETS",
    "STYLES",
    "Config",
    "load_config",
    "load_config_file",
    "parse_config",
    "resolve_ruleset",
]
