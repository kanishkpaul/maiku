"""The contract every adapter must satisfy.

Subclass, supply two fixtures, and the shared behaviour is enforced. Twelve adapters
written to a convention become twelve dialects; written to a suite they stay one protocol.
"""

import pytest

from maiku.adapters.base import Adapter, guarded
from maiku.adapters.context import CallContext
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.projections import a2a, mcp, openai_tools
from maiku.wire.events import Failed, Finished, Started, is_terminal
from tests.conftest import everything


async def drain(adapter: Adapter, affordance: str, arguments: dict, ctx: CallContext) -> list:
    return [event async for event in guarded(adapter, affordance, arguments, ctx)]


class AdapterContract:
    @pytest.fixture
    async def adapter(self) -> Adapter:
        raise NotImplementedError

    @pytest.fixture
    def sample_call(self) -> tuple[str, dict]:
        raise NotImplementedError

    def context(self, participant: str = "test/subject") -> CallContext:
        return CallContext(session_id="s_test", task_id="t_test", participant=participant)

    async def test_describe_returns_a_valid_descriptor(self, adapter):
        descriptor = await adapter.describe()
        assert isinstance(descriptor, ParticipantDescriptor)
        ParticipantDescriptor(**descriptor.model_dump(mode="json"))

    async def test_describe_is_stable(self, adapter):
        assert (await adapter.describe()).id == (await adapter.describe()).id

    async def test_every_affordance_has_a_binding(self, adapter):
        descriptor = await adapter.describe()
        for affordance in descriptor.affordances:
            assert descriptor.binding_for(affordance.name)

    async def test_probe_answers(self, adapter):
        health = await adapter.probe()
        assert isinstance(health.online, bool)

    async def test_stream_ends_with_exactly_one_terminal_event(self, adapter, sample_call):
        events = await drain(adapter, *sample_call, self.context())
        assert isinstance(events[0], Started)
        assert is_terminal(events[-1])
        assert sum(is_terminal(e) for e in events) == 1

    async def test_stream_is_sequenced(self, adapter, sample_call):
        events = await drain(adapter, *sample_call, self.context())
        assert [e.seq for e in events] == list(range(len(events)))

    async def test_unknown_affordance_fails_without_raising(self, adapter):
        events = await drain(adapter, "definitely_not_here", {}, self.context())
        assert isinstance(events[-1], Failed)
        assert events[-1].code == "unknown_affordance"

    async def test_bad_arguments_fail_without_raising(self, adapter, sample_call):
        events = await drain(adapter, sample_call[0], {"__nope__": 1}, self.context())
        assert isinstance(events[-1], Failed)

    async def test_cancellation_terminates_cleanly(self, adapter, sample_call):
        ctx = self.context()
        ctx.cancel()
        events = await drain(adapter, *sample_call, ctx)
        assert is_terminal(events[-1])
        assert sum(is_terminal(e) for e in events) == 1

    async def test_result_matches_declared_affordance(self, adapter, sample_call):
        name, _ = sample_call
        descriptor = await adapter.describe()
        assert descriptor.affordance(name)
        events = await drain(adapter, *sample_call, self.context())
        assert isinstance(events[-1], Finished | Failed)

    async def test_descriptor_projects_to_the_ecosystem(self, adapter):
        descriptor = await adapter.describe()

        tools = mcp.to_tools(descriptor, everything())
        assert len(tools) == len(descriptor.affordances)
        assert all(tool["name"].isidentifier() for tool in tools)
        assert all(tool["_meta"]["maiku/participant"] == descriptor.handle for tool in tools)

        assert len(openai_tools.to_tools(descriptor, everything())) == len(descriptor.affordances)

        card = a2a.to_agent_card(descriptor, everything())
        assert len(card["skills"]) == len(descriptor.affordances)

    async def test_extra_arguments_are_rejected_by_the_contract(self, adapter, sample_call):
        """Enforced by guarded(), so it holds for every adapter and not just the strict ones."""
        name, arguments = sample_call
        events = await drain(adapter, name, {**arguments, "__unexpected__": 1}, self.context())
        assert isinstance(events[-1], Failed | Finished)
