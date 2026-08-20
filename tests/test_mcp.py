"""The MCP server, exercised in memory rather than over a subprocess."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="the MCP server needs the optional 'mcp' extra")

from mcp.client import Client

from debabble.mcp_server import mcp, resolve_project


@pytest.fixture
async def client():
    async with Client(mcp) as connected:
        yield connected


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_the_expected_tools_are_offered(client):
    names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"lint", "lint_files", "get_style_rules", "explain_rule", "list_rules"}


async def test_every_tool_describes_itself(client):
    for tool in (await client.list_tools()).tools:
        assert tool.description, f"{tool.name} has no description for the model to read"


async def test_lint_reports_findings(client):
    result = await client.call_tool(
        "lint", {"text": "Great question! I hope this helps.", "register": "prose"}
    )
    payload = result.structured_content

    assert payload["clean"] is False
    assert payload["banned"] >= 2
    rules = {f["rule"] for f in payload["findings"]}
    assert "chat-artifacts.sycophancy" in rules


async def test_lint_reports_clean_text_as_clean(client):
    result = await client.call_tool(
        "lint", {"text": "The cache expires after 300 seconds.", "register": "prose"}
    )
    assert result.structured_content["clean"] is True
    assert result.structured_content["findings"] == []


async def test_lint_rejects_an_unknown_register(client):
    result = await client.call_tool("lint", {"text": "x", "register": "sideways"})
    assert result.is_error


async def test_get_style_rules_returns_the_rules(client):
    result = await client.call_tool("get_style_rules", {"style": "minimal"})
    text = result.content[0].text

    assert text.startswith("# Writing rules")
    assert "Never" in text


async def test_get_style_rules_honours_the_style(client):
    minimal = (await client.call_tool("get_style_rules", {"style": "minimal"})).content[0].text
    compact = (await client.call_tool("get_style_rules", {"style": "compact"})).content[0].text

    assert len(minimal) < len(compact)


async def test_get_style_rules_rejects_an_unknown_style(client):
    result = await client.call_tool("get_style_rules", {"style": "fancy"})
    assert result.is_error


async def test_explain_rule_returns_something_pasteable(client):
    result = await client.call_tool("explain_rule", {"rule_id": "vocabulary.hype-verbs"})
    payload = result.structured_content

    assert payload["id"] == "vocabulary.hype-verbs"
    assert payload["severity"] == "ban"
    assert payload["instruction"]
    assert "[[rules]]" in payload["toml"]


async def test_explain_rule_names_alternatives_when_asked_for_nonsense(client):
    result = await client.call_tool("explain_rule", {"rule_id": "does.not-exist"})
    assert result.is_error
    assert "Known rules" in str(result.content[0].text)


async def test_list_rules_covers_the_packs(client):
    payload = (await client.call_tool("list_rules", {})).structured_content
    ids = {p["id"] for p in payload["packs"]}

    assert "chat-artifacts" in ids
    assert all(p["rules"] for p in payload["packs"])


async def test_list_rules_can_be_narrowed_to_one_pack(client):
    payload = (await client.call_tool("list_rules", {"pack": "chat-artifacts"})).structured_content
    assert [p["id"] for p in payload["packs"]] == ["chat-artifacts"]


async def test_the_rewrite_prompt_carries_the_text(client):
    result = await client.get_prompt("rewrite", {"text": "Great question!"})
    body = "\n".join(m.content.text for m in result.messages if getattr(m.content, "text", None))

    assert "Great question!" in body
    assert "$ARGUMENTS" not in body


async def test_the_styleguide_resource_reads(client):
    result = await client.read_resource("debabble://styleguide")
    assert "Writing rules" in result.contents[0].text


def test_the_project_is_found_from_an_explicit_argument(tmp_path):
    assert resolve_project(str(tmp_path)) == tmp_path


def test_a_bad_project_argument_falls_back_rather_than_crashing(tmp_path):
    assert resolve_project(str(tmp_path / "nope")) is None


def test_the_project_is_found_from_the_claude_variable(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert resolve_project() == tmp_path.resolve()
