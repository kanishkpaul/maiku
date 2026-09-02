"""A model calling the other participants, through the ordinary router path."""

import json

import httpx
import pytest

from maiku.descriptor.enums import SideEffect
from maiku.runtime.delegate import delegate, toolset
from maiku.runtime.grants import Capability
from maiku.runtime.workspace import Workspace

SAMPLE = "python:tests.fixtures.sample_module"
EFFECTS = "python:tests.fixtures.effects_module"
script: list[dict] = []


def sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def turn(content="", calls=()):
    """One scripted assistant turn, streamed the way a real provider streams it."""
    body = b""
    if content:
        body += sse({"choices": [{"delta": {"content": content}}]})
    for index, (name, arguments) in enumerate(calls):
        # Split across chunks, exactly as providers do.
        body += sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": index,
                                    "id": f"c{index}",
                                    "function": {"name": name, "arguments": ""},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        for piece in (json.dumps(arguments)[i : i + 5] for i in range(0, 200, 5)):
            if piece:
                body += sse(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {"index": index, "function": {"arguments": piece}}
                                    ]
                                }
                            }
                        ]
                    }
                )
    body += sse({"choices": [{"finish_reason": "tool_calls" if calls else "stop"}]})
    return body + b"data: [DONE]\n\n"


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": []})
    seen.append(json.loads(request.content))
    return httpx.Response(200, content=script.pop(0))


seen: list[dict] = []


@pytest.fixture(autouse=True)
def reset():
    script.clear()
    seen.clear()


@pytest.fixture
async def session(tmp_path, monkeypatch):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        await ws.add(EFFECTS)
        await ws.add("ollama:planner")

        async with ws.session() as s:
            original = s.router.adapter_for

            async def patched(handle):
                adapter = await original(handle)
                if handle == "ollama/planner":
                    return adapter.with_client(
                        httpx.AsyncClient(transport=httpx.MockTransport(handler))
                    )
                return adapter

            monkeypatch.setattr(s.router, "adapter_for", patched)
            yield s


async def test_the_model_is_handed_the_others_as_tools(session):
    script.append(turn(content="nothing to do"))
    await delegate(session, "ollama/planner", "hello")

    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert "test_sample__score" in names
    assert "test_effects__publish" in names
    # A model offered itself as a tool will eventually call itself.
    assert not any(n.startswith("ollama_planner") for n in names)


async def test_using_restricts_the_toolset(session):
    script.append(turn(content="ok"))
    await delegate(session, "ollama/planner", "hi", using=["test/sample", "ollama/planner"])

    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert all(n.startswith("test_sample") for n in names)


async def test_a_tool_call_actually_runs_the_participant(session):
    script.append(turn(calls=[("test_sample__fetch", {"key": "abc"})]))
    script.append(turn(content="It resolved to ABC."))

    outcome = await delegate(session, "ollama/planner", "look up abc")

    assert outcome.answer == "It resolved to ABC."
    assert outcome.delegated == ["test/sample#fetch"]
    assert outcome.steps[0].result == {"key": "abc", "value": "ABC"}
    assert outcome.turns == 2


async def test_the_tool_result_is_fed_back_to_the_model(session):
    script.append(turn(calls=[("test_sample__fetch", {"key": "xyz"})]))
    script.append(turn(content="done"))
    await delegate(session, "ollama/planner", "go")

    tool_messages = [m for m in seen[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "XYZ" in tool_messages[0]["content"]


async def test_two_calls_in_one_turn_both_run(session):
    script.append(
        turn(
            calls=[
                ("test_sample__fetch", {"key": "a"}),
                ("test_sample__score", {"text": "hello"}),
            ]
        )
    )
    script.append(turn(content="both done"))
    outcome = await delegate(session, "ollama/planner", "go")

    assert outcome.delegated == ["test/sample#fetch", "test/sample#score"]
    assert all(step.ok for step in outcome.steps)


async def test_a_grant_decides_what_the_model_is_even_offered(session):
    """The grant is what makes a tool exist for this caller, not a filter applied later."""
    grant = session.grant(
        "planner",
        capabilities=[
            Capability.parse("ollama/planner#chat"),
            Capability.parse("test/sample#fetch"),
        ],
        max_side_effect=SideEffect.READ,
        scopes=set(),
    )
    _, routes = toolset(session.participants(), exclude={"ollama/planner"}, grant=grant)
    assert "test_sample__fetch" in routes
    assert "test_effects__publish" not in routes


async def test_a_grant_stops_a_delegated_call(session):
    """The model may ask for what it was never shown; the grant still decides."""
    session.grant(
        "planner",
        capabilities=[
            Capability.parse("ollama/planner#chat"),
            Capability.parse("test/sample#fetch"),
        ],
        max_side_effect=SideEffect.READ,
        scopes=set(),
    )
    script.append(turn(calls=[("test_effects__publish", {"message": "everywhere"})]))
    script.append(turn(content="I was not allowed to."))

    outcome = await delegate(session, "ollama/planner", "publish it", caller="planner")

    assert not outcome.steps[0].ok
    assert outcome.answer == "I was not allowed to."


async def test_a_refusal_is_handed_back_so_the_model_can_recover(session):
    script.append(turn(calls=[("test_sample__fetch", {"wrong": "argument"})]))
    script.append(turn(calls=[("test_sample__fetch", {"key": "corrected"})]))
    script.append(turn(content="fixed it"))

    outcome = await delegate(session, "ollama/planner", "go")

    assert "invalid_arguments" in outcome.steps[0].error
    assert outcome.steps[1].ok
    assert outcome.answer == "fixed it"


async def test_an_unknown_tool_name_is_reported_not_raised(session):
    script.append(turn(calls=[("no_such__tool", {})]))
    script.append(turn(content="ok"))
    outcome = await delegate(session, "ollama/planner", "go")
    assert "no such tool" in outcome.steps[0].error


async def test_a_loop_is_bounded(session):
    script.extend(turn(calls=[("test_sample__fetch", {"key": "again"})]) for _ in range(4))
    outcome = await delegate(session, "ollama/planner", "go", max_turns=3)

    assert outcome.exhausted
    assert outcome.turns == 3


async def test_delegated_calls_are_recorded_like_any_other(session):
    script.append(turn(calls=[("test_sample__fetch", {"key": "a"})]))
    script.append(turn(content="done"))
    await delegate(session, "ollama/planner", "go", caller="planner")

    called = [t.participant for t in session.router.tasks.values()]
    assert called.count("test/sample") == 1
    assert called.count("ollama/planner") == 2
    assert any(p.author == "test/sample" for p in session.space.history())


async def test_a_caller_that_cannot_reach_the_model_is_told_why(session):
    from maiku.runtime.grants import Denied

    session.grant("planner", capabilities=[Capability.parse("test/sample#fetch")])
    with pytest.raises(Denied, match="include ollama/planner in the grant"):
        await delegate(session, "ollama/planner", "go", caller="planner")
