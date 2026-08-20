"""Loading rule packs from TOML.

One loader serves every source of rules: the packs bundled with debabble, custom
pack files a user drops in a folder, and inline rule overrides written straight
into ``debabble.toml``. They all speak the same field names, so anything you can
read in a shipped pack you can also write in your own config.
"""

from __future__ import annotations

import difflib
import re
import tomllib
from dataclasses import fields as dataclass_fields
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import PackError
from .models import (
    CHANNELS,
    KINDS,
    REGISTERS,
    RULE_SCOPES,
    UNITS,
    Pack,
    Rule,
    Severity,
    validate_choice,
    validate_choices,
)

# Rule fields that hold a tuple of strings in the model but a list in TOML.
_RULE_FIELDS = {f.name for f in dataclass_fields(Rule)}
_PACK_KEYS = {"id", "title", "description", "version", "references", "default", "priority"}


def did_you_mean(name: str, known) -> str:
    """A trailing suggestion for a mistyped name, or nothing when none is close."""
    close = difflib.get_close_matches(name, sorted(known), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def build_rule(data: dict[str, Any], *, pack_id: str, where: str) -> Rule:
    """Turn one ``[[rules]]`` table into a :class:`Rule`.

    ``id`` may be short (``delve``) or qualified (``vocabulary.delve``); short
    ids are qualified with the pack they are defined in.
    """
    unknown = set(data) - _RULE_FIELDS
    if unknown:
        name = min(unknown)
        raise PackError(f"{where}: unknown rule field {name!r}.{did_you_mean(name, _RULE_FIELDS)}")

    raw_id = str(data.get("id", "")).strip()
    if not raw_id:
        raise PackError(f"{where}: every rule needs an 'id'.")
    rule_id = raw_id if "." in raw_id else f"{pack_id}.{raw_id}"

    instruction = str(data.get("instruction", "")).strip()
    if not instruction:
        raise PackError(
            f"{where}: rule {rule_id!r} needs an 'instruction' (what the writer should do)."
        )

    kwargs: dict[str, Any] = {"id": rule_id, "instruction": instruction}

    if "severity" in data:
        kwargs["severity"] = Severity.parse(data["severity"], where=f"{where}: rule {rule_id!r}")
    if "kind" in data:
        kwargs["kind"] = validate_choice(
            str(data["kind"]), KINDS, where=f"{where}: rule {rule_id!r} kind"
        )
    if "scope" in data:
        kwargs["scope"] = validate_choice(
            str(data["scope"]), RULE_SCOPES, where=f"{where}: rule {rule_id!r} scope"
        )
    if "unit" in data:
        kwargs["unit"] = validate_choice(
            str(data["unit"]), UNITS, where=f"{where}: rule {rule_id!r} unit"
        )
    if "registers" in data:
        kwargs["registers"] = validate_choices(
            data["registers"], REGISTERS, where=f"{where}: rule {rule_id!r} registers"
        )
    if "channels" in data:
        kwargs["channels"] = validate_choices(
            data["channels"], CHANNELS, where=f"{where}: rule {rule_id!r} channels"
        )

    for key in ("words", "phrases", "suggest"):
        if key in data:
            value = data[key]
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, (list, tuple)):
                raise PackError(
                    f"{where}: rule {rule_id!r} field {key!r} must be a list of strings."
                )
            kwargs[key] = tuple(str(v) for v in value)

    for key in ("title", "pattern", "wrong", "right", "why", "fix", "replacement", "era"):
        if key in data:
            kwargs[key] = str(data[key])

    if "max" in data:
        value = data["max"]
        if value is not None and not isinstance(value, int):
            raise PackError(f"{where}: rule {rule_id!r} field 'max' must be a whole number.")
        kwargs["max"] = value
    if "per_words" in data:
        if not isinstance(data["per_words"], int) or data["per_words"] <= 0:
            raise PackError(
                f"{where}: rule {rule_id!r} field 'per_words' must be a positive whole number."
            )
        kwargs["per_words"] = data["per_words"]

    rule = Rule(**kwargs)
    _check_rule_consistency(rule, where=where)
    return rule


def _check_rule_consistency(rule: Rule, *, where: str) -> None:
    """Catch rules that can never match, so mistakes surface at load time."""
    if rule.kind == "wordlist" and not rule.words:
        raise PackError(f"{where}: rule {rule.id!r} is kind 'wordlist' but lists no 'words'.")
    if rule.kind == "phrase" and not rule.phrases:
        raise PackError(f"{where}: rule {rule.id!r} is kind 'phrase' but lists no 'phrases'.")
    if rule.kind == "regex" and not rule.pattern:
        raise PackError(f"{where}: rule {rule.id!r} is kind 'regex' but has no 'pattern'.")
    if rule.pattern:
        # Compile now so a typo is reported against the file that holds it,
        # rather than crashing later inside the linter.
        try:
            re.compile(rule.pattern)
        except re.error as err:
            raise PackError(
                f"{where}: rule {rule.id!r} has a pattern that is not valid: {err}"
            ) from err
    if rule.fix and rule.fix != "safe":
        raise PackError(
            f"{where}: rule {rule.id!r} has fix={rule.fix!r}; the only supported value is 'safe'."
        )
    if rule.fix == "safe" and not (rule.suggest or rule.replacement):
        raise PackError(
            f"{where}: rule {rule.id!r} is marked fix='safe' but offers no 'suggest' or 'replacement' text."
        )


def build_pack(data: dict[str, Any], *, source: str) -> Pack:
    """Turn a parsed pack file into a :class:`Pack`."""
    meta = data.get("pack")
    if not isinstance(meta, dict):
        raise PackError(f"{source}: a pack file needs a [pack] table with at least an 'id'.")

    unknown = set(meta) - _PACK_KEYS
    if unknown:
        name = min(unknown)
        raise PackError(f"{source}: unknown [pack] field {name!r}.{did_you_mean(name, _PACK_KEYS)}")

    pack_id = str(meta.get("id", "")).strip()
    if not pack_id:
        raise PackError(f"{source}: [pack] needs an 'id'.")

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise PackError(f"{source}: 'rules' must be a list of [[rules]] tables.")

    rules = tuple(build_rule(r, pack_id=pack_id, where=source) for r in raw_rules)

    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            raise PackError(f"{source}: duplicate rule id {rule.id!r}.")
        seen.add(rule.id)

    references = meta.get("references", [])
    if isinstance(references, str):
        references = [references]

    return Pack(
        id=pack_id,
        title=str(meta.get("title", pack_id)),
        description=str(meta.get("description", "")),
        rules=rules,
        version=str(meta.get("version", "")),
        references=tuple(str(r) for r in references),
        default=bool(meta.get("default", True)),
        priority=int(meta.get("priority", 50)),
        source=source,
    )


def rule_to_toml(rule: Rule) -> str:
    """One rule as a pasteable [[rules]] block.

    Both `debabble rules <id>` and the MCP explain_rule tool promise the same
    text, so they call the same function.
    """
    import tomlkit

    from .config import rule_to_dict

    return tomlkit.dumps({"rules": [rule_to_dict(rule)]}).rstrip()


def load_pack_file(path: Path, *, source: str | None = None) -> Pack:
    """Read and validate one pack TOML file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise PackError(f"{path}: not valid TOML — {err}") from err
    except OSError as err:
        raise PackError(f"{path}: could not be read — {err}") from err
    return build_pack(data, source=source or str(path))


BUILTIN_PACK_DIR = Path(__file__).parent / "data" / "packs"


def builtin_pack_files() -> list[Path]:
    """The pack files shipped inside the installed package."""
    return sorted(BUILTIN_PACK_DIR.glob("*.toml"))


@lru_cache(maxsize=1)
def load_builtin_packs() -> tuple[Pack, ...]:
    """Load every pack bundled with debabble.

    Cached: these ship inside the wheel and cannot change while the process
    runs, and parsing the ten files was most of the wall time of a command.
    """
    return tuple(load_pack_file(p, source="built-in") for p in builtin_pack_files())


def discover_packs(directories: list[Path]) -> list[Pack]:
    """Load custom packs from the given directories, if they exist.

    Any ``*.toml`` file in a ``packs/`` directory is loaded exactly like a
    bundled pack, so custom packs are shareable by committing them to a repo.
    """
    found: list[Pack] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.toml")):
            found.append(load_pack_file(path))
    return found


def load_all_packs(custom_dirs: list[Path] | None = None) -> list[Pack]:
    """Bundled packs plus any custom packs, with custom packs replacing same-id bundled ones."""
    packs = {p.id: p for p in load_builtin_packs()}
    for pack in discover_packs(custom_dirs or []):
        packs[pack.id] = pack
    return list(packs.values())


__all__ = [
    "build_pack",
    "build_rule",
    "builtin_pack_files",
    "did_you_mean",
    "discover_packs",
    "load_all_packs",
    "load_builtin_packs",
    "load_pack_file",
]
