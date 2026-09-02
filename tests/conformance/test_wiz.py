"""A WiZ light exposes LAN state without bypassing Maiku's adapter contract."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pywizlight.bulb import PilotParser

from maiku.adapters.context import CallContext
from maiku.adapters.registry import open_participant
from maiku.adapters.wiz import CHANGED, READ, WRITE, WizAdapter
from maiku.descriptor import AffordanceKind, AffordanceOperation, SideEffect, Transport
from maiku.wire.events import Delta, Finished
from tests.conformance.contract import AdapterContract, drain


@dataclass
class FakeKelvinRange:
    min: int = 2200
    max: int = 6500


class FakeBulb:
    ip = "192.0.2.55"
    port = 38899
    mac = "AABBCCDDEEFF"

    def __init__(self) -> None:
        self.raw = {"mac": self.mac, "state": False, "dimming": 42, "temp": 3000}
        self.sent: list[dict] = []
        self.callback = None
        self.push_cancel = None
        self.push_running = False
        self.closed = False
        self.bulb_type = SimpleNamespace(
            name="ESP25_SHRGB_31",
            fw_version="1.33.0",
            features=SimpleNamespace(
                brightness=True, color_tmp=True, color=True, dual_head=False
            ),
            kelvin_range=FakeKelvinRange(),
        )

    async def get_bulbtype(self):
        return self.bulb_type

    async def getMac(self):
        return self.mac

    async def updateState(self):
        return [PilotParser(dict(self.raw))]

    async def send(self, message):
        self.sent.append(message)
        self.raw.update(message["params"])
        if self.callback:
            self.callback([PilotParser(dict(self.raw))])
        return {"result": {"success": True}}

    async def start_push(self, callback):
        self.callback = callback
        self.push_running = True
        self.push_cancel = lambda: None
        return True

    async def async_close(self):
        self.closed = True


async def wiz_adapter() -> tuple[WizAdapter, FakeBulb]:
    adapter = await open_participant("wiz:192.0.2.55?mac=AABBCCDDEEFF")
    assert isinstance(adapter, WizAdapter)
    bulb = FakeBulb()
    return adapter.with_bulb(bulb), bulb


class TestWizParticipant(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter, _ = await wiz_adapter()
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return READ, {}


async def test_descriptor_separates_read_write_and_event_authority():
    adapter, _ = await wiz_adapter()
    descriptor = await adapter.describe()
    read = descriptor.affordance(READ)
    write = descriptor.affordance(WRITE)
    changed = descriptor.affordance(CHANGED)

    assert (read.kind, read.operation, read.side_effects) == (
        AffordanceKind.PROPERTY,
        AffordanceOperation.READ,
        SideEffect.READ,
    )
    assert (write.kind, write.operation, write.side_effects) == (
        AffordanceKind.PROPERTY,
        AffordanceOperation.WRITE,
        SideEffect.WRITE,
    )
    assert (changed.kind, changed.operation) == (
        AffordanceKind.EVENT,
        AffordanceOperation.SUBSCRIBE,
    )
    assert descriptor.bindings[0].transport is Transport.UDP
    assert descriptor.bindings[0].auth.scheme == "none"


async def test_read_returns_normalized_state():
    adapter, _ = await wiz_adapter()
    events = await drain(adapter, READ, {}, AdapterContract().context("wiz/aabbccddeeff"))
    assert events[-1].result == {
        "on": False,
        "brightness": 107,
        "color_temperature": 3000,
    }


async def test_write_uses_local_set_pilot_and_returns_observed_state():
    adapter, bulb = await wiz_adapter()
    events = await drain(
        adapter,
        WRITE,
        {"on": True, "brightness": 191},
        AdapterContract().context("wiz/aabbccddeeff"),
    )
    assert bulb.sent == [
        {"method": "setPilot", "params": {"state": True, "dimming": 75}}
    ]
    assert events[-1].result == {"on": True, "brightness": 191, "color_temperature": 3000}


async def test_push_subscription_emits_normalized_change_and_cancels():
    adapter, bulb = await wiz_adapter()
    ctx = CallContext(session_id="s", task_id="t", participant="wiz/aabbccddeeff")
    events = []

    async def consume():
        async for event in drain_stream(adapter, ctx):
            events.append(event)

    task = asyncio.create_task(consume())
    while bulb.callback is None:
        await asyncio.sleep(0)
    bulb.raw.update({"state": True, "dimming": 50})
    bulb.callback([PilotParser(dict(bulb.raw))])
    while not any(isinstance(event, Delta) for event in events):
        await asyncio.sleep(0)
    ctx.cancel()
    await task

    deltas = [event for event in events if isinstance(event, Delta)]
    assert deltas[0].part.data == {
        "on": True,
        "brightness": 128,
        "color_temperature": 3000,
    }
    assert sum(isinstance(event, Finished) for event in events) == 1
    assert bulb.push_running is False


async def drain_stream(adapter: WizAdapter, ctx: CallContext):
    from maiku.adapters.base import guarded

    async for event in guarded(adapter, CHANGED, {}, ctx):
        yield event
