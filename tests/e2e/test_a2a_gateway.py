"""Anything adapted is also reachable as an A2A agent."""

import sys

import pytest

from maiku.descriptor.affordance import Affordance
from maiku.gateways.a2a_server import A2AGateway, arguments_from
from maiku.projections.naming import handle_slug
from maiku.runtime.grants import Capability
from maiku.runtime.workspace import Workspace

SAMPLE = "python:tests.fixtures.sample_module"
VISION = "python:tests.fixtures.vision_module"
UPSTREAM = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"


@pytest.fixture
async def gateway(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        await ws.add(VISION)
        async with ws.session() as session:
            yield A2AGateway(session, base_url="http://host:8080", grant=session.root_grant)


def send(skill, text=None, data=None, message_id=1):
    parts = []
    if text is not None:
        parts.append({"kind": "text", "text": text})
    if data is not None:
        parts.append({"kind": "data", "data": data})
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": parts, "metadata": {"maiku/skill": skill}}},
    }


def test_a_data_part_is_taken_as_arguments():
    affordance = Affordance(name="x", summary="x")
    message = {"parts": [{"kind": "data", "data": {"a": 1}}]}
    assert arguments_from(message, affordance) == {"a": 1}


def test_json_text_is_taken_as_arguments():
    affordance = Affordance(name="x", summary="x")
    message = {"parts": [{"kind": "text", "text": '{"a": 2}'}]}
    assert arguments_from(message, affordance) == {"a": 2}


def test_plain_text_fills_the_single_required_string():
    affordance = Affordance(
        name="x",
        summary="x",
        input_schema={
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    )
    message = {"parts": [{"kind": "text", "text": "why"}]}
    assert arguments_from(message, affordance) == {"question": "why"}


async def test_the_aggregate_card_lists_every_affordance(gateway):
    card = gateway.agent_card()
    assert card["protocolVersion"] == "0.3.0"
    ids = {s["id"] for s in card["skills"]}
    assert "test_sample__score" in ids
    assert "local_vision__logits" in ids


async def test_each_participant_also_has_its_own_card(gateway):
    card = gateway.agent_card("local_vision")
    assert card["name"] == "vision_module"
    assert card["url"] == "http://host:8080/agents/local_vision"
    assert {s["id"] for s in card["skills"]} == {"logits", "embed", "classify_file", "render"}
    assert gateway.agent_card("nobody") is None


async def test_sending_a_message_runs_the_call(gateway):
    response = await gateway.rpc(send("test_sample__fetch", data={"key": "abc"}))
    task = response["result"]

    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["parts"][0]["text"] == '{"key": "abc", "value": "ABC"}'


async def test_a_scoped_agent_takes_the_bare_skill_name(gateway):
    response = await gateway.rpc(send("fetch", data={"key": "z"}), slug="test_sample")
    assert response["result"]["status"]["state"] == "completed"


async def test_a_failing_call_becomes_a_failed_task(gateway):
    response = await gateway.rpc(send("test_sample__fetch", data={"wrong": 1}))
    task = response["result"]
    assert task["status"]["state"] == "failed"
    assert "invalid_arguments" in task["status"]["message"]["parts"][0]["text"]


async def test_a_missing_skill_is_an_invalid_params_error(gateway):
    assert (await gateway.rpc(send("nope__nope")))["error"]["code"] == -32602
    assert (await gateway.rpc(send("")))["error"]["code"] == -32602


async def test_an_unknown_method_is_a_protocol_error(gateway):
    response = await gateway.rpc({"jsonrpc": "2.0", "id": 1, "method": "nonsense"})
    assert response["error"]["code"] == -32601


async def test_notifications_get_no_reply(gateway):
    assert await gateway.rpc({"jsonrpc": "2.0", "method": "message/send"}) is None


async def test_tasks_can_be_fetched_afterwards(gateway):
    task_id = (await gateway.rpc(send("test_sample__fetch", data={"key": "a"})))["result"]["id"]
    fetched = await gateway.rpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task_id}}
    )
    assert fetched["result"]["id"] == task_id
    assert fetched["result"]["status"]["state"] == "completed"

    missing = await gateway.rpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tasks/get", "params": {"id": "nope"}}
    )
    assert missing["error"]["code"] == -32602


async def test_artifacts_are_returned_as_a2a_artifacts(gateway):
    response = await gateway.rpc(send("local_vision__render", data={"width": 4, "height": 2}))
    files = [
        part
        for artifact in response["result"]["artifacts"]
        for part in artifact["parts"]
        if part["kind"] == "file"
    ]
    assert len(files) == 1
    assert files[0]["file"]["uri"].startswith("maiku://artifact/sha256:")


async def test_an_mcp_server_can_be_served_out_over_a2a(tmp_path):
    """In through MCP, out through A2A. Neither side is aware of the other."""
    with Workspace(tmp_path / "home") as ws:
        await ws.add(UPSTREAM)
        async with ws.session() as session:
            gateway = A2AGateway(session, grant=session.root_grant)
            response = await gateway.rpc(send("mcp_fixture__read_file", data={"path": "notes.md"}))

    assert response["result"]["artifacts"][0]["parts"][0]["text"] == "contents of notes.md"


async def test_a_gateway_with_no_grant_offers_no_skills(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        async with ws.session() as session:
            gateway = A2AGateway(session, grant=None)

            assert gateway.agent_card()["skills"] == []
            assert gateway.agent_card(handle_slug("test/sample")) is None


async def test_the_agent_card_is_filtered_by_the_clients_grant(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        async with ws.session() as session:
            guest = A2AGateway(
                session,
                grant=session.grant("guest", capabilities=[Capability.parse("test/sample#fetch")]),
            )
            card = guest.agent_card(handle_slug("test/sample"))
            assert [s["id"] for s in card["skills"]] == ["fetch"]

            operator = A2AGateway(session, grant=session.root_grant)
            assert len(operator.agent_card(handle_slug("test/sample"))["skills"]) > 1


async def test_agent_card_returns_none_when_grant_covers_no_affordances(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        async with ws.session() as session:
            stranger_grant = session.grant(
                "stranger", capabilities=[Capability.parse("somewhere/else#nothing")]
            )
            gateway = A2AGateway(session, base_url="http://localhost:8080", grant=stranger_grant)
            slug = handle_slug("test/sample")
            assert gateway.agent_card(slug) is None
            assert gateway.agent_card()["skills"] == []
