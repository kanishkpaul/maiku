"""A physical thing uses the same grants, approvals and event stream as every model."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from maiku.adapters.base import Adapter, UnknownAffordance
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor import (
    Affordance,
    AffordanceKind,
    AffordanceOperation,
    Approval,
    Binding,
    Determinism,
    Display,
    Kind,
    LatencyClass,
    ParticipantDescriptor,
    Permissions,
    Residency,
    RuntimeInfo,
    SideEffect,
    Transport,
)
from maiku.runtime.grants import Capability
from maiku.runtime.session import CallFailed
from maiku.runtime.workspace import Workspace
from maiku.wire.events import Delta, Event, Finished, NeedsApproval, is_terminal
from maiku.wire.parts import DataPart
from maiku.wire.task import TaskState
from tests.conformance.contract import AdapterContract

EMPTY_INPUT = {"type": "object", "properties": {}, "additionalProperties": False}
LIGHT_STATE = {
    "type": "object",
    "properties": {"on": {"type": "boolean"}},
    "required": ["on"],
    "additionalProperties": False,
}


@register
class PhysicalLightAdapter(Adapter):
    scheme = "physical_test"
    on = False

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "PhysicalLightAdapter":
        return cls()

    async def describe(self) -> ParticipantDescriptor:
        return ParticipantDescriptor(
            handle="physical/light",
            kind=Kind.ROBOT,
            display=Display(name="Contract light", description="A stateful physical fixture"),
            runtime=RuntimeInfo(residency=Residency.LOCAL_SERVICE),
            affordances=[
                Affordance(
                    name="read_on",
                    summary="Read whether the light is on",
                    kind=AffordanceKind.PROPERTY,
                    operation=AffordanceOperation.READ,
                    input_schema=EMPTY_INPUT,
                    output_schema=LIGHT_STATE,
                    determinism=Determinism.DETERMINISTIC,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.READ,
                ),
                Affordance(
                    name="write_on",
                    summary="Change whether the light is on",
                    kind=AffordanceKind.PROPERTY,
                    operation=AffordanceOperation.WRITE,
                    input_schema=LIGHT_STATE,
                    output_schema=LIGHT_STATE,
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.WRITE,
                ),
                Affordance(
                    name="on_changed",
                    summary="Watch the light's on state",
                    kind=AffordanceKind.EVENT,
                    operation=AffordanceOperation.SUBSCRIBE,
                    input_schema=EMPTY_INPUT,
                    output_schema={},
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.READ,
                ),
            ],
            bindings=[Binding(scheme=self.scheme, transport=Transport.IN_PROCESS)],
            permissions=Permissions(side_effects=SideEffect.WRITE, approval=Approval.ON_SCOPE),
        )

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        raise UnknownAffordance(f"{affordance!r} is not invokable")
        yield  # pragma: no cover - keeps this an async iterator

    async def read_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != "read_on":
            raise UnknownAffordance(affordance)
        yield Finished(result={"on": type(self).on})

    async def write_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != "write_on":
            raise UnknownAffordance(affordance)
        type(self).on = arguments["on"]
        yield Finished(result={"on": type(self).on})

    async def subscribe(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != "on_changed":
            raise UnknownAffordance(affordance)
        yield Delta(part=DataPart(data={"on": type(self).on}))
        while True:
            ctx.raise_if_cancelled()
            await asyncio.sleep(0.001)


class TestPhysicalParticipantContract(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        return PhysicalLightAdapter()

    @pytest.fixture
    def sample_call(self):
        return "read_on", {}


@pytest.fixture
async def workspace(tmp_path):
    PhysicalLightAdapter.on = False
    with Workspace(tmp_path / "home") as ws:
        await ws.add("physical_test:light")
        yield ws


async def approve_all(request):
    return True


async def test_read_and_write_dispatch_to_distinct_adapter_operations(workspace):
    async with workspace.session(responder=approve_all) as session:
        assert await session.result("physical/light", "read_on") == {"on": False}
        assert await session.result("physical/light", "write_on", {"on": True}) == {"on": True}
        assert await session.result("physical/light", "read_on") == {"on": True}


async def test_read_only_grant_cannot_write_the_same_property_participant(workspace):
    async with workspace.session() as session:
        session.grant(
            "observer",
            capabilities=[Capability.parse("physical/light")],
            max_side_effect=SideEffect.READ,
        )
        assert await session.result("physical/light", "read_on", caller="observer") == {
            "on": False
        }

        with pytest.raises(CallFailed) as caught:
            await session.result(
                "physical/light", "write_on", {"on": True}, caller="observer"
            )
        assert caught.value.event.code == "denied"
        assert PhysicalLightAdapter.on is False


async def test_property_write_requires_approval_but_read_does_not(workspace):
    requests: list[NeedsApproval] = []
    observed: list[Event] = []

    async def approve(request):
        requests.append(request)
        return True

    async with workspace.session(
        responder=approve,
        observer=lambda session_id, event: observed.append(event),
    ) as session:
        await session.result("physical/light", "read_on")
        assert requests == []
        await session.result("physical/light", "write_on", {"on": True})

    assert len(requests) == 1
    assert sum(isinstance(event, NeedsApproval) for event in observed) == 1
    assert requests[0].side_effects == SideEffect.WRITE.value
    assert PhysicalLightAdapter.on is True


async def test_event_subscription_terminates_exactly_once_on_cancel(workspace):
    async with workspace.session() as session:
        events = []
        async for event in session.call("physical/light", "on_changed"):
            events.append(event)
            if isinstance(event, Delta):
                task = next(task for task in session.router.tasks.values() if not task.done)
                assert session.router.cancel(task.id)

    assert events[-1].state is TaskState.CANCELED
    assert sum(is_terminal(event) for event in events) == 1
