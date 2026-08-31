"""Driven against a real MCP server subprocess, not a mock."""

import sys

import pytest

from maiku.adapters.mcp_client import side_effect_from
from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import Kind, Residency, SideEffect
from maiku.runtime.artifacts import ArtifactStore, ScopedArtifacts
from maiku.wire.events import ArtifactWritten, Failed
from tests.conformance.contract import AdapterContract, drain

SERVER = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"


class TestMCPServer(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant(SERVER)
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "read_file", {"path": "README.md"}


@pytest.fixture
async def adapter():
    adapter = await open_participant(SERVER)
    yield adapter
    await adapter.close()


async def test_tools_become_affordances(adapter):
    descriptor = await adapter.describe()
    assert descriptor.kind is Kind.TOOL
    assert descriptor.runtime.residency is Residency.SUBPROCESS
    assert descriptor.handle == "mcp/fixture"
    assert {a.name for a in descriptor.affordances} == {
        "read_file",
        "delete_everything",
        "render_chart",
        "unwritten",
    }


async def test_server_info_lands_in_provenance(adapter):
    descriptor = await adapter.describe()
    assert descriptor.provenance.version == "9.9.9"
    assert descriptor.display.name == "Fixture Server"


async def test_behavioural_hints_become_side_effects(adapter):
    descriptor = await adapter.describe()
    assert descriptor.affordance("read_file").side_effects is SideEffect.READ
    assert descriptor.affordance("read_file").idempotent
    assert descriptor.affordance("delete_everything").side_effects is SideEffect.IRREVERSIBLE
    assert descriptor.worst_side_effect is SideEffect.IRREVERSIBLE


def test_an_unannotated_tool_is_not_assumed_safe():
    assert side_effect_from({}) is SideEffect.WRITE


async def test_unannotated_tool_defaults_to_write(adapter):
    descriptor = await adapter.describe()
    assert descriptor.affordance("unwritten").side_effects is SideEffect.WRITE


async def test_calling_a_tool_returns_its_text(adapter):
    events = await drain(adapter, "read_file", {"path": "x.md"}, AdapterContract().context())
    assert events[-1].result == "contents of x.md"


async def test_an_error_result_becomes_a_failed_event(adapter):
    events = await drain(adapter, "delete_everything", {}, AdapterContract().context())
    assert isinstance(events[-1], Failed)
    assert "refused" in events[-1].message


async def test_binary_content_becomes_an_artifact(adapter, tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ctx = AdapterContract().context()
    ctx.artifacts = ScopedArtifacts(store)

    events = await drain(adapter, "render_chart", {"title": "sales"}, ctx)
    written = [e for e in events if isinstance(e, ArtifactWritten)]

    assert len(written) == 1
    assert written[0].ref.media_type == "image/png"
    assert (await store.read(written[0].ref.digest)).startswith(b"\x89PNG")
    assert events[-1].result == "chart: sales"


async def test_probe_notices_a_dead_server(adapter):
    await adapter.close()
    health = await adapter.probe()
    assert not health.online


async def test_a_command_that_does_not_exist_is_unreachable():
    from maiku.adapters.base import Unreachable

    with pytest.raises(Unreachable):
        await open_participant("mcp:definitely-not-a-real-binary-xyz")


async def test_mcp_survives_a_round_trip_through_maiku(adapter):
    """Ingest an MCP server, project it back to MCP, and lose nothing that matters."""
    from maiku.projections import a2a, mcp

    descriptor = await adapter.describe()
    tools = {t["_meta"]["maiku/affordance"]: t for t in mcp.to_tools(descriptor)}

    assert tools["read_file"]["annotations"]["readOnlyHint"] is True
    assert tools["read_file"]["annotations"]["idempotentHint"] is True
    assert tools["delete_everything"]["annotations"]["destructiveHint"] is True
    assert tools["read_file"]["inputSchema"]["required"] == ["path"]

    # And the same participant now speaks a protocol MCP has no notion of.
    card = a2a.to_agent_card(descriptor, base_url="https://host/a2a")
    assert {s["id"] for s in card["skills"]} == set(tools)


async def test_approval_policy_can_be_demanded_at_adapt_time():
    from maiku.descriptor.enums import Approval

    adapter = await open_participant(f"{SERVER}?approval=on_scope")
    try:
        assert (await adapter.describe()).permissions.approval is Approval.ON_SCOPE
    finally:
        await adapter.close()

    assert (await (await open_participant(SERVER)).describe()).permissions.approval is (
        Approval.NEVER
    )
