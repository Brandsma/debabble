"""Rewriting text through a configured model backend.

The linter can point at AI-speak, but turning a sentence into plain writing
needs a model, and which model is a personal choice rather than a project one.
So the backend lives under ``[rewrite]`` in the global config, and every
backend is reached without adding a dependency: the claude CLI and user
commands are subprocesses, and OpenAI-compatible APIs are one HTTP request
through the standard library.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import paths
from .errors import ConfigError, DebabbleError
from .models import RuleSet
from .render import render_rewrite_command

BACKENDS = ("claude-cli", "openai", "command")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_KEY_ENV = "OPENAI_API_KEY"

_REWRITE_KEYS = {"backend", "base_url", "model", "api_key_env", "command"}


class RewriteError(DebabbleError):
    """A rewrite backend failed, or is not set up to run."""


@dataclass(frozen=True, slots=True)
class RewriteSettings:
    """The ``[rewrite]`` section: which model rewrites text, and how to reach it."""

    backend: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = ""
    api_key_env: str = DEFAULT_KEY_ENV
    command: str = ""


def parse_rewrite_table(data: object, *, where: str) -> RewriteSettings:
    """Turn a ``[rewrite]`` table into settings, refusing typos.

    Only the shape is checked here. Whether a backend has everything it needs,
    such as a model name, is checked when a rewrite actually runs, so an
    unfinished section does not stop `apply` or `lint` from working.
    """
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: [rewrite] must be a table.")
    unknown = set(data) - _REWRITE_KEYS
    if unknown:
        raise ConfigError(
            f"{where}: unknown key {min(unknown)!r} in [rewrite]. "
            f"Valid keys are: {', '.join(sorted(_REWRITE_KEYS))}."
        )
    for key in sorted(_REWRITE_KEYS):
        if key in data and not isinstance(data[key], str):
            raise ConfigError(f"{where}: rewrite.{key} must be a string.")

    backend = str(data.get("backend", "")).strip()
    if backend and backend not in BACKENDS:
        raise ConfigError(
            f"{where}: rewrite.backend is {backend!r}; use one of: {', '.join(BACKENDS)}."
        )
    return RewriteSettings(
        backend=backend,
        base_url=str(data.get("base_url", "")).strip() or DEFAULT_BASE_URL,
        model=str(data.get("model", "")).strip(),
        api_key_env=str(data.get("api_key_env", "")).strip() or DEFAULT_KEY_ENV,
        command=str(data.get("command", "")).strip(),
    )


def _rewrite_table(path: Path) -> RewriteSettings | None:
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path}: not valid TOML — {err}") from err
    except OSError as err:
        raise ConfigError(f"{path}: could not be read — {err}") from err
    if "rewrite" not in data:
        return None
    return parse_rewrite_table(data["rewrite"], where=str(path))


def load_settings(project_root: Path | None) -> RewriteSettings:
    """The backend in effect: the global config, unless the project sets its own.

    The rule profile treats a project config as self-contained, but the
    backend is machine-level state, so it is read from the global config even
    when the project has its own file. A project ``[rewrite]`` section still
    wins when one exists, for repositories that standardise on one backend.
    """
    settings = _rewrite_table(paths.global_config_file()) or RewriteSettings()
    if project_root is not None:
        project = _rewrite_table(paths.project_config_file(project_root))
        if project is not None:
            settings = project
    return settings


def save_settings(settings: RewriteSettings) -> Path:
    """Write the settings into the global config, keeping the rest of the file."""
    import tomlkit

    path = paths.global_config_file()
    if path.is_file():
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        document = tomlkit.document()
    if "rewrite" not in document:
        document["rewrite"] = tomlkit.table()
    table = document["rewrite"]

    # Keys the chosen backend does not use are dropped, so the file says only
    # what is in effect and a later switch does not leave stale settings.
    for key in sorted(_REWRITE_KEYS):
        if key in table:
            del table[key]
    table["backend"] = settings.backend
    if settings.backend == "openai":
        table["base_url"] = settings.base_url
        table["model"] = settings.model
        table["api_key_env"] = settings.api_key_env
    if settings.backend == "command":
        table["command"] = settings.command

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


# Prompts


def build_prompt(ruleset: RuleSet, *, style: str, text: str) -> str:
    """The full prompt: the rules, the rewrite task, and the text itself."""
    return render_rewrite_command(ruleset, style=style).replace("$ARGUMENTS", text)


def build_instructions(ruleset: RuleSet, *, style: str) -> str:
    """The prompt without the text, for backends that take a system message."""
    return render_rewrite_command(ruleset, style=style).replace("$ARGUMENTS", "").rstrip() + "\n"


# Backends


def run(settings: RewriteSettings, ruleset: RuleSet, *, style: str, text: str) -> str:
    """Rewrite ``text`` with the configured backend and return the result."""
    if settings.backend == "claude-cli":
        return _run_claude_cli(build_prompt(ruleset, style=style, text=text))
    if settings.backend == "openai":
        return _run_openai(settings, build_instructions(ruleset, style=style), text)
    if settings.backend == "command":
        return _run_command(settings, build_prompt(ruleset, style=style, text=text))
    raise ConfigError("No rewrite backend is configured. Run `debabble rewrite --configure`.")


def _finished_or_error(finished: subprocess.CompletedProcess, name: str) -> str:
    if finished.returncode != 0:
        detail = finished.stderr.strip() or finished.stdout.strip() or "no output"
        raise RewriteError(f"{name} exited with {finished.returncode}: {detail}")
    return finished.stdout.strip()


def _run_claude_cli(prompt: str) -> str:
    executable = shutil.which("claude")
    if executable is None:
        raise RewriteError(
            "The claude CLI is not on PATH. Install Claude Code, or pick another "
            "backend with `debabble rewrite --configure`."
        )
    # The prompt goes over stdin: a full-style rule set is longer than some
    # platforms allow a single argument to be.
    finished = subprocess.run(
        [executable, "-p"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return _finished_or_error(finished, "claude -p")


def _run_command(settings: RewriteSettings, prompt: str) -> str:
    if not settings.command:
        raise ConfigError(
            'The "command" backend needs a command. Run `debabble rewrite --configure`.'
        )
    finished = subprocess.run(
        settings.command,
        shell=True,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return _finished_or_error(finished, repr(settings.command))


def _run_openai(settings: RewriteSettings, instructions: str, text: str) -> str:
    if not settings.model:
        raise ConfigError('The "openai" backend needs a model. Run `debabble rewrite --configure`.')
    key = os.environ.get(settings.api_key_env, "").strip()
    if not key:
        raise RewriteError(
            f"The environment variable {settings.api_key_env} is empty. Export your "
            "API key there, or point at another variable with `debabble rewrite --configure`."
        )

    url = settings.base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": text},
            ],
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as err:
        raise RewriteError(f"{url} answered {err.code}: {_http_detail(err)}") from err
    except (URLError, TimeoutError) as err:
        reason = getattr(err, "reason", err)
        raise RewriteError(f"{url} could not be reached: {reason}") from err
    except json.JSONDecodeError as err:
        raise RewriteError(f"{url} answered with something that is not JSON.") from err

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as err:
        raise RewriteError(f"{url} answered without a message. Reply: {str(body)[:200]}") from err
    return str(content).strip()


def _http_detail(err: HTTPError) -> str:
    """The server's own error message when it sent one, else the HTTP reason."""
    try:
        payload = json.loads(err.read().decode("utf-8"))
    except (OSError, ValueError):
        return str(err.reason)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return str(err.reason)


__all__ = [
    "BACKENDS",
    "DEFAULT_BASE_URL",
    "DEFAULT_KEY_ENV",
    "RewriteError",
    "RewriteSettings",
    "build_instructions",
    "build_prompt",
    "load_settings",
    "parse_rewrite_table",
    "run",
    "save_settings",
]
