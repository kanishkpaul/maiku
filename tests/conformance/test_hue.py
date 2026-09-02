"""A Hue light exposes physical state without bypassing Maiku's adapter contract."""

import json

import httpx
import pytest

from maiku.adapters.base import AdapterError
from maiku.adapters.hue import CHANGED, READ, WRITE, HueAdapter
from maiku.adapters.registry import open_participant
from maiku.descriptor import AffordanceKind, AffordanceOperation, SideEffect
from maiku.wire.events import Delta
from tests.conformance.contract import AdapterContract, drain

BRIDGE = "https://192.0.2.10"
LIGHT_ID = "11111111-2222-3333-4444-555555555555"
LIGHT = {
    "id": LIGHT_ID,
    "type": "light",
    "metadata": {"name": "Desk lamp"},
    "on": {"on": False},
    "dimming": {"brightness": 42.0},
}
seen: list[httpx.Request] = []


def handler(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    if request.url.path in {
        "/clip/v2/resource/light",
        f"/clip/v2/resource/light/{LIGHT_ID}",
    } and request.method == "GET":
        return httpx.Response(200, json={"data": [LIGHT], "errors": []})
    if request.url.path == f"/clip/v2/resource/light/{LIGHT_ID}" and request.method == "PUT":
        update = json.loads(request.content)
        if "on" in update:
            LIGHT["on"] = update["on"]
        if "dimming" in update:
            LIGHT["dimming"] = update["dimming"]
        return httpx.Response(
            200,
            json={"data": [{"rid": LIGHT_ID, "rtype": "light"}], "errors": []},
        )
    if request.url.path == "/eventstream/clip/v2":
        event = [{"type": "update", "data": [{"id": LIGHT_ID, "on": {"on": True}}]}]
        return httpx.Response(
            200,
            text=f"event: update\ndata: {json.dumps(event)}\n\n",
            headers={"content-type": "text/event-stream"},
        )
    return httpx.Response(404)


def stub() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def hue_adapter(uri: str | None = None) -> HueAdapter:
    raw = uri or f"hue:{BRIDGE}?light={LIGHT_ID}&key_env=HUE_TEST_KEY"
    adapter = await open_participant(raw)
    assert isinstance(adapter, HueAdapter)
    return adapter.with_client(stub())


@pytest.fixture(autouse=True)
def hue_key(monkeypatch):
    seen.clear()
    LIGHT["on"] = {"on": False}
    LIGHT["dimming"] = {"brightness": 42.0}
    monkeypatch.setenv("HUE_TEST_KEY", "not-a-real-key")


class TestHueParticipant(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await hue_adapter()
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return READ, {}


async def test_descriptor_separates_read_write_and_event_authority():
    descriptor = await (await hue_adapter()).describe()
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


async def test_read_returns_normalized_state():
    adapter = await hue_adapter()
    events = await drain(adapter, READ, {}, AdapterContract().context("hue/desk-lamp"))
    assert events[-1].result == {"on": False, "brightness": 42.0}


async def test_write_uses_clip_v2_shape_and_returns_observed_state():
    adapter = await hue_adapter()
    events = await drain(
        adapter,
        WRITE,
        {"on": True, "brightness": 75.0},
        AdapterContract().context("hue/desk-lamp"),
    )
    put = next(request for request in seen if request.method == "PUT")
    assert json.loads(put.content) == {
        "on": {"on": True},
        "dimming": {"brightness": 75.0},
    }
    assert events[-1].result == {"on": True, "brightness": 75.0}


async def test_event_stream_emits_only_updates_for_this_light():
    adapter = await hue_adapter()
    events = await drain(adapter, CHANGED, {}, AdapterContract().context("hue/desk-lamp"))
    deltas = [event for event in events if isinstance(event, Delta)]
    assert [delta.part.data for delta in deltas] == [{"id": LIGHT_ID, "on": {"on": True}}]


async def test_application_key_is_referenced_not_stored():
    descriptor = await (await hue_adapter()).describe()
    binding = descriptor.bindings[0]
    assert binding.auth.env_var == "HUE_TEST_KEY"
    assert "not-a-real-key" not in descriptor.model_dump_json()
    assert all(request.headers["hue-application-key"] == "not-a-real-key" for request in seen)


async def test_missing_application_key_is_a_legible_error(monkeypatch):
    monkeypatch.delenv("HUE_TEST_KEY")
    with pytest.raises(AdapterError, match="HUE_TEST_KEY"):
        await (await hue_adapter()).describe()


async def test_multiple_lights_require_an_explicit_choice():
    second = LIGHT | {"id": "another", "metadata": {"name": "Other"}}

    def many(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [LIGHT, second], "errors": []})

    adapter = await open_participant(f"hue:{BRIDGE}?key_env=HUE_TEST_KEY")
    adapter = adapter.with_client(httpx.AsyncClient(transport=httpx.MockTransport(many)))
    with pytest.raises(AdapterError, match=r"\?light=<id>"):
        await adapter.describe()
