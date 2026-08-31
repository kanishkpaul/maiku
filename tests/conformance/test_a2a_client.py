"""A remote A2A agent, ingested."""

import base64
import json

import httpx
import pytest

from maiku.adapters.a2a_client import card_url
from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import AffordanceKind, Kind, Residency
from maiku.runtime.artifacts import ArtifactStore, ScopedArtifacts
from maiku.wire.events import ArtifactWritten, Failed
from tests.conformance.contract import AdapterContract, drain

AGENT = "https://agent.test"
CARD = {
    "protocolVersion": "0.3.0",
    "name": "Researcher",
    "description": "Finds things out",
    "url": f"{AGENT}/a2a",
    "version": "3.0.1",
    "provider": {"organization": "acme"},
    "capabilities": {"streaming": True},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/pdf"],
    "skills": [
        {"id": "search", "name": "Search the web", "tags": ["research"]},
        {"id": "summarise", "name": "Summarise a document"},
    ],
}

PDF = base64.b64encode(b"%PDF-1.7 fake").decode()
state = {"polls": 0, "mode": "task"}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("agent-card.json"):
        return httpx.Response(200, json=CARD)
    if request.url.path != "/a2a":
        return httpx.Response(404)

    body = json.loads(request.content)
    method, params = body["method"], body["params"]

    if method == "message/send":
        if state["mode"] == "message":
            return _ok(body, {"kind": "message", "parts": [{"kind": "text", "text": "direct"}]})
        if state["mode"] == "error":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -1, "message": "nope"}},
            )
        state["polls"] = 0
        return _ok(body, {"id": "t1", "status": {"state": "working"}})

    if method == "tasks/get":
        state["polls"] += 1
        if state["polls"] < 2:
            return _ok(body, {"id": params["id"], "status": {"state": "working"}})
        if state["mode"] == "failing":
            return _ok(
                body,
                {
                    "id": params["id"],
                    "status": {
                        "state": "failed",
                        "message": {"parts": [{"kind": "text", "text": "could not"}]},
                    },
                },
            )
        return _ok(
            body,
            {
                "id": params["id"],
                "status": {"state": "completed"},
                "artifacts": [
                    {
                        "artifactId": "a1",
                        "name": "report",
                        "parts": [
                            {"kind": "text", "text": "the answer"},
                            {
                                "kind": "file",
                                "file": {
                                    "bytes": PDF,
                                    "mimeType": "application/pdf",
                                    "name": "report.pdf",
                                },
                            },
                        ],
                    }
                ],
            },
        )
    return httpx.Response(404)


def _ok(body: dict, result: dict) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


async def agent(uri: str = f"a2a:{AGENT}?poll=0.001"):
    return (await open_participant(uri)).with_client(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


@pytest.fixture(autouse=True)
def reset():
    state.update(polls=0, mode="task")


class TestA2AAgent(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await agent()
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "search", {"message": "what is a widget"}


def test_card_url_is_derived_or_used_as_given():
    assert card_url("https://x.test") == "https://x.test/.well-known/agent-card.json"
    assert card_url("https://x.test/card.json") == "https://x.test/card.json"


async def test_skills_become_affordances():
    descriptor = await (await agent()).describe()
    assert descriptor.kind is Kind.AGENT
    assert descriptor.runtime.residency is Residency.REMOTE
    assert descriptor.handle == "a2a/researcher"
    assert {a.name for a in descriptor.affordances} == {"search", "summarise"}
    assert descriptor.affordance("search").kind is AffordanceKind.STREAM
    assert descriptor.provenance.version == "3.0.1"


async def test_a_task_is_followed_to_completion():
    events = await drain(
        await agent(), "search", {"message": "hello"}, AdapterContract().context()
    )
    assert any(e.type == "progress" for e in events)
    assert events[-1].result == "the answer"


async def test_file_parts_become_artifacts(tmp_path):
    ctx = AdapterContract().context()
    store = ArtifactStore(tmp_path / "artifacts")
    ctx.artifacts = ScopedArtifacts(store)

    events = await drain(await agent(), "search", {"message": "hello"}, ctx)
    written = [e for e in events if isinstance(e, ArtifactWritten)]

    assert len(written) == 1
    assert written[0].ref.media_type == "application/pdf"
    assert (await store.read(written[0].ref.digest)).startswith(b"%PDF")


async def test_an_immediate_message_reply_needs_no_polling():
    state["mode"] = "message"
    events = await drain(
        await agent(), "search", {"message": "hello"}, AdapterContract().context()
    )
    assert events[-1].result == "direct"
    assert state["polls"] == 0


async def test_a_failed_remote_task_becomes_a_failed_event():
    state["mode"] = "failing"
    events = await drain(
        await agent(), "search", {"message": "hello"}, AdapterContract().context()
    )
    assert isinstance(events[-1], Failed)
    assert "could not" in events[-1].message


async def test_a_jsonrpc_error_becomes_a_failed_event():
    state["mode"] = "error"
    events = await drain(
        await agent(), "search", {"message": "hello"}, AdapterContract().context()
    )
    assert isinstance(events[-1], Failed)
    assert "nope" in events[-1].message


async def test_an_ingested_agent_projects_back_out_to_a2a():
    from maiku.projections import a2a, mcp

    descriptor = await (await agent()).describe()
    card = a2a.to_agent_card(descriptor, base_url=f"{AGENT}/a2a")

    assert card["name"] == CARD["name"]
    assert {s["id"] for s in card["skills"]} == {s["id"] for s in CARD["skills"]}
    assert card["capabilities"]["streaming"] is True

    # And the same agent is now callable as MCP tools, which A2A alone cannot express.
    assert {t["_meta"]["maiku/affordance"] for t in mcp.to_tools(descriptor)} == {
        "search",
        "summarise",
    }


async def test_a_non_http_target_is_rejected():
    from maiku.adapters.base import AdapterError

    with pytest.raises(AdapterError):
        await open_participant("a2a:not-a-url")
