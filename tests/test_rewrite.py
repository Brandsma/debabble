"""The rewrite backends, without any real model behind them."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from debabble import rewrite
from debabble.config import Config, parse_config, resolve_ruleset
from debabble.errors import ConfigError


@pytest.fixture
def ruleset(monkeypatch, tmp_path):
    monkeypatch.setattr("debabble.paths.global_packs_dir", lambda: tmp_path / "nowhere")
    return resolve_ruleset(Config())


@pytest.fixture
def global_dir(monkeypatch, tmp_path):
    directory = tmp_path / "global"
    directory.mkdir()
    monkeypatch.setattr("debabble.paths.user_config_dir", lambda: directory)
    return directory


# ---------------------------------------------------------------------------
# The [rewrite] section
# ---------------------------------------------------------------------------


def test_a_typo_in_the_section_is_refused():
    with pytest.raises(ConfigError) as err:
        parse_config({"rewrite": {"bakend": "claude-cli"}})
    assert "bakend" in str(err.value)


def test_an_unknown_backend_lists_the_real_ones():
    with pytest.raises(ConfigError) as err:
        parse_config({"rewrite": {"backend": "telepathy"}})
    assert "claude-cli" in str(err.value)


def test_an_incomplete_section_does_not_break_config_loading():
    """Missing model or command fails when rewriting, not when applying."""
    parse_config({"rewrite": {"backend": "openai"}})


def test_settings_come_from_the_global_config(global_dir):
    (global_dir / "debabble.toml").write_text(
        '[rewrite]\nbackend = "openai"\nmodel = "some-model"\n', encoding="utf-8"
    )
    settings = rewrite.load_settings(None)
    assert settings.backend == "openai"
    assert settings.model == "some-model"
    assert settings.base_url == rewrite.DEFAULT_BASE_URL


def test_a_project_rewrite_section_wins(global_dir, tmp_path):
    (global_dir / "debabble.toml").write_text(
        '[rewrite]\nbackend = "claude-cli"\n', encoding="utf-8"
    )
    project = tmp_path / "proj"
    project.mkdir()
    (project / "debabble.toml").write_text(
        '[rewrite]\nbackend = "command"\ncommand = "my-model"\n', encoding="utf-8"
    )
    settings = rewrite.load_settings(project)
    assert settings.backend == "command"
    assert settings.command == "my-model"


def test_a_project_without_a_section_keeps_the_global_backend(global_dir, tmp_path):
    """The rule profile is self-contained per project; the backend is not."""
    (global_dir / "debabble.toml").write_text(
        '[rewrite]\nbackend = "claude-cli"\n', encoding="utf-8"
    )
    project = tmp_path / "proj"
    project.mkdir()
    (project / "debabble.toml").write_text('[profile]\nstyle = "minimal"\n', encoding="utf-8")
    assert rewrite.load_settings(project).backend == "claude-cli"


def test_no_config_means_no_backend(global_dir):
    assert rewrite.load_settings(None).backend == ""


def test_saving_keeps_the_rest_of_the_file(global_dir):
    path = global_dir / "debabble.toml"
    path.write_text('# my note\n[profile]\nstyle = "minimal"\n', encoding="utf-8")

    rewrite.save_settings(
        rewrite.RewriteSettings(
            backend="openai", base_url="https://example.test/v1", model="m", api_key_env="MY_KEY"
        )
    )
    text = path.read_text(encoding="utf-8")
    assert "# my note" in text
    assert 'style = "minimal"' in text
    assert rewrite.load_settings(None).model == "m"

    # Switching backends drops the keys the new one does not use.
    rewrite.save_settings(rewrite.RewriteSettings(backend="claude-cli"))
    assert "model" not in path.read_text(encoding="utf-8")


def test_saving_creates_the_global_config(global_dir):
    rewrite.save_settings(rewrite.RewriteSettings(backend="claude-cli"))
    assert rewrite.load_settings(None).backend == "claude-cli"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_the_prompt_holds_the_rules_and_the_text(ruleset):
    prompt = rewrite.build_prompt(ruleset, style="minimal", text="Great question!")
    assert "## Task" in prompt
    assert prompt.rstrip().endswith("Great question!")
    assert "$ARGUMENTS" not in prompt


def test_the_instructions_leave_the_text_out(ruleset):
    instructions = rewrite.build_instructions(ruleset, style="minimal")
    assert "## Task" in instructions
    assert "$ARGUMENTS" not in instructions


# ---------------------------------------------------------------------------
# The claude-cli backend
# ---------------------------------------------------------------------------


def test_claude_cli_gets_the_prompt_on_stdin(monkeypatch, ruleset):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["input"] = kwargs["input"]
        return subprocess.CompletedProcess(argv, 0, stdout="Clean text.\n", stderr="")

    monkeypatch.setattr(rewrite.shutil, "which", lambda name: "/somewhere/claude")
    monkeypatch.setattr(rewrite.subprocess, "run", fake_run)

    settings = rewrite.RewriteSettings(backend="claude-cli")
    result = rewrite.run(settings, ruleset, style="minimal", text="Great question!")

    assert result == "Clean text."
    assert seen["argv"] == ["/somewhere/claude", "-p"]
    assert "Great question!" in seen["input"]
    assert "## Task" in seen["input"]


def test_a_missing_claude_cli_names_the_way_out(monkeypatch, ruleset):
    monkeypatch.setattr(rewrite.shutil, "which", lambda name: None)
    settings = rewrite.RewriteSettings(backend="claude-cli")
    with pytest.raises(rewrite.RewriteError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "--configure" in str(err.value)


def test_a_failing_backend_reports_its_stderr(monkeypatch, ruleset):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="broke down")

    monkeypatch.setattr(rewrite.shutil, "which", lambda name: "/somewhere/claude")
    monkeypatch.setattr(rewrite.subprocess, "run", fake_run)

    settings = rewrite.RewriteSettings(backend="claude-cli")
    with pytest.raises(rewrite.RewriteError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "broke down" in str(err.value)


# ---------------------------------------------------------------------------
# The command backend
# ---------------------------------------------------------------------------


def test_the_command_backend_pipes_through_a_real_process(tmp_path, ruleset):
    script = tmp_path / "shout.py"
    script.write_text("import sys; sys.stdout.write(sys.stdin.read().upper())", encoding="utf-8")

    settings = rewrite.RewriteSettings(backend="command", command=f'"{sys.executable}" "{script}"')
    result = rewrite.run(settings, ruleset, style="minimal", text="make this loud")
    assert "MAKE THIS LOUD" in result


def test_the_command_backend_without_a_command_is_an_error(ruleset):
    settings = rewrite.RewriteSettings(backend="command")
    with pytest.raises(ConfigError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "--configure" in str(err.value)


# ---------------------------------------------------------------------------
# The openai backend
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_openai_sends_the_key_and_reads_the_reply(monkeypatch, ruleset):
    seen = {}

    def fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "Clean text.\n"}}]})

    monkeypatch.setattr(rewrite, "urlopen", fake_urlopen)
    monkeypatch.setenv("MY_TEST_KEY", "sk-test")

    settings = rewrite.RewriteSettings(
        backend="openai",
        base_url="https://example.test/v1",
        model="some-model",
        api_key_env="MY_TEST_KEY",
    )
    result = rewrite.run(settings, ruleset, style="minimal", text="Great question!")

    assert result == "Clean text."
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["payload"]["model"] == "some-model"
    assert seen["payload"]["messages"][0]["role"] == "system"
    assert seen["payload"]["messages"][1]["content"] == "Great question!"


def test_openai_without_a_key_names_the_variable(monkeypatch, ruleset):
    monkeypatch.delenv("MY_TEST_KEY", raising=False)
    settings = rewrite.RewriteSettings(backend="openai", model="m", api_key_env="MY_TEST_KEY")
    with pytest.raises(rewrite.RewriteError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "MY_TEST_KEY" in str(err.value)


def test_openai_without_a_model_is_an_error(monkeypatch, ruleset):
    monkeypatch.setenv("MY_TEST_KEY", "sk-test")
    settings = rewrite.RewriteSettings(backend="openai", api_key_env="MY_TEST_KEY")
    with pytest.raises(ConfigError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "--configure" in str(err.value)


def test_a_reply_without_a_message_is_reported(monkeypatch, ruleset):
    monkeypatch.setattr(rewrite, "urlopen", lambda *a, **k: FakeResponse({"error": "nope"}))
    monkeypatch.setenv("MY_TEST_KEY", "sk-test")
    settings = rewrite.RewriteSettings(backend="openai", model="m", api_key_env="MY_TEST_KEY")
    with pytest.raises(rewrite.RewriteError) as err:
        rewrite.run(settings, ruleset, style="minimal", text="x")
    assert "without a message" in str(err.value)
