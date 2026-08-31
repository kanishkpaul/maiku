"""Anything adapted becomes a tool an MCP client can call."""

import json
import sys

import pytest

from maiku.gateways.mcp_server import MCPGateway
from maiku.runtime.workspace import Workspace

SAMPLE = "python:tests.fixtures.sample_module"
UPSTREAM = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"


@pytest.fixture
async def gateway(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        await ws.add("human:kanishk?channel=unreachable")
        async with ws.session() as session:
            yield MCPGateway(session)


def rpc(method, params=None, message_id=1):
    return {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}}


async def test_initialize_handshake(gateway):
    result = (await gateway.handle(rpc("initialize")))["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"]["tools"]["listChanged"] is True
    assert result["serverInfo"]["name"] == "maiku"


async def test_notifications_get_no_reply(gateway):
    assert await gateway.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


async def test_unknown_method_is_a_protocol_error(gateway):
    response = await gateway.handle(rpc("nonsense/method"))
    assert response["error"]["code"] == -32601


async def test_every_affordance_is_listed_as_a_tool(gateway):
    tools = (await gateway.handle(rpc("tools/list")))["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "test_sample__score" in names
    assert "human_kanishk__approve" in names
    assert all(t["name"].isidentifier() for t in tools)


async def test_a_python_function_is_callable_as_a_tool(gateway):
    result = (
        await gateway.handle(
            rpc("tools/call", {"name": "test_sample__score", "arguments": {"text": "x" * 50}})
        )
    )["result"]
    assert result["isError"] is False
    assert float(result["content"][0]["text"]) == pytest.approx(1.0)


async def test_structured_results_are_returned_structured(gateway):
    result = (
        await gateway.handle(
            rpc("tools/call", {"name": "test_sample__fetch", "arguments": {"key": "abc"}})
        )
    )["result"]
    assert result["structuredContent"] == {"key": "abc", "value": "ABC"}
    assert json.loads(result["content"][0]["text"])["value"] == "ABC"


async def test_bad_arguments_come_back_as_a_tool_error_not_a_crash(gateway):
    result = (
        await gateway.handle(
            rpc("tools/call", {"name": "test_sample__score", "arguments": {"nope": 1}})
        )
    )["result"]
    assert result["isError"] is True
    assert "invalid_arguments" in result["content"][0]["text"]


async def test_unknown_tool_is_reported_clearly(gateway):
    result = (await gateway.handle(rpc("tools/call", {"name": "no_such__tool"})))["result"]
    assert result["isError"] is True
    assert "no participant matching" in result["content"][0]["text"]


async def test_a_participant_added_mid_session_appears_without_a_restart(gateway):
    before = {t["name"] for t in gateway.tools()}
    await gateway.session.workspace.add("python:tests.fixtures.deploy_module")
    after = {t["name"] for t in gateway.tools()}
    assert after - before == {"test_deploy__deploy", "test_deploy__dry_run"}


async def test_an_mcp_server_can_be_re_served_through_maiku(tmp_path):
    """Ingest an MCP server, then hand it back out to an MCP client."""
    with Workspace(tmp_path / "home") as ws:
        await ws.add(UPSTREAM)
        async with ws.session() as session:
            gateway = MCPGateway(session)
            result = (
                await gateway.handle(
                    rpc(
                        "tools/call",
                        {"name": "mcp_fixture__read_file", "arguments": {"path": "a.md"}},
                    )
                )
            )["result"]

    assert result["content"][0]["text"] == "contents of a.md"


async def test_artifacts_come_back_as_resource_links(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(UPSTREAM)
        async with ws.session() as session:
            gateway = MCPGateway(session)
            result = (
                await gateway.handle(
                    rpc(
                        "tools/call",
                        {"name": "mcp_fixture__render_chart", "arguments": {"title": "q4"}},
                    )
                )
            )["result"]

    links = [b for b in result["content"] if b["type"] == "resource_link"]
    assert len(links) == 1
    assert links[0]["mimeType"] == "image/png"
    assert links[0]["uri"].startswith("maiku://artifact/sha256:")
