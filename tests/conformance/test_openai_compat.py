"""The chat adapter, driven against a stub server rather than a live model."""

import json

import httpx
import pytest

from maiku.adapters.openai_compat import OpenAICompatible
from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import Device, Residency
from maiku.wire.events import Delta, Failed, Usage
from tests.conformance.contract import AdapterContract, drain

PIECES = ["Hel", "lo ", "there"]


def sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def chat_stream() -> bytes:
    body = b"".join(sse({"choices": [{"delta": {"content": piece}}]}) for piece in PIECES)
    body += sse(
        {
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
    )
    return body + b"data: [DONE]\n\n"


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "stub-model"}]})
    if request.url.path.endswith("/chat/completions"):
        body = json.loads(request.content)
        if body.get("model") == "explodes":
            return httpx.Response(500, text="model is on fire")
        return httpx.Response(200, content=chat_stream())
    return httpx.Response(404)


def stub_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def stub_adapter(uri: str = "ollama:stub-model") -> OpenAICompatible:
    return (await open_participant(uri)).with_client(stub_client())


class TestOpenAICompatible(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await stub_adapter()
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "complete", {"prompt": "hi"}


@pytest.mark.parametrize(
    ("uri", "handle", "residency", "device"),
    [
        ("openai:gpt-4o", "openai/gpt-4o", Residency.REMOTE, Device.NONE),
        ("ollama:qwen3:8b", "ollama/qwen3:8b", Residency.LOCAL_SERVICE, Device.MPS),
        ("openrouter:x/y", "openrouter/x/y", Residency.REMOTE, Device.NONE),
    ],
)
async def test_flavours_only_differ_in_defaults(uri, handle, residency, device):
    descriptor = await (await stub_adapter(uri)).describe()
    assert descriptor.handle == handle
    assert descriptor.runtime.residency is residency
    assert descriptor.runtime.device is device
    assert {a.name for a in descriptor.affordances} == {"chat", "complete"}


async def test_base_url_can_be_overridden():
    adapter = await stub_adapter("openai:local?base=http://127.0.0.1:9000/v1")
    descriptor = await adapter.describe()
    assert descriptor.bindings[0].uri == "http://127.0.0.1:9000/v1/chat/completions"


async def test_streaming_deltas_and_usage():
    adapter = await stub_adapter()
    events = await drain(adapter, "complete", {"prompt": "hi"}, AdapterContract().context())

    assert [e.part.text for e in events if isinstance(e, Delta)] == PIECES
    usage = next(e for e in events if isinstance(e, Usage))
    assert (usage.tokens_in, usage.tokens_out) == (7, 3)
    assert events[-1].result == "Hello there"


async def test_prompt_is_folded_into_messages():
    seen = {}

    def capture(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            seen.update(json.loads(request.content))
            return httpx.Response(200, content=chat_stream())
        return httpx.Response(404)

    adapter = (await open_participant("ollama:m")).with_client(
        httpx.AsyncClient(transport=httpx.MockTransport(capture))
    )
    await drain(
        adapter, "complete", {"prompt": "hi", "system": "be terse"}, AdapterContract().context()
    )
    assert seen["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]
    assert seen["stream"] is True


async def test_server_errors_surface_as_failed_not_exceptions():
    adapter = await stub_adapter("ollama:explodes")
    events = await drain(adapter, "complete", {"prompt": "hi"}, AdapterContract().context())
    assert isinstance(events[-1], Failed)
    assert events[-1].code == "unreachable"
    assert events[-1].retryable is True


async def test_probe_uses_the_models_endpoint():
    assert (await stub_adapter()).probe
    health = await (await stub_adapter()).probe()
    assert health.online


async def test_probe_reports_a_dead_server():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = (await open_participant("ollama:m")).with_client(
        httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )
    health = await adapter.probe()
    assert not health.online
    assert "ConnectError" in health.detail
