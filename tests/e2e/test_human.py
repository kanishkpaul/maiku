"""A person is a participant, and the escalation path is an ordinary call."""

import pytest

from maiku.adapters.channels import (
    CallbackChannel,
    UnreachableChannel,
    register_channel,
)
from maiku.descriptor.enums import Kind, LatencyClass, Residency
from maiku.runtime.escalation import first_available, route_to
from maiku.runtime.session import CallFailed
from maiku.runtime.workspace import Workspace

DEPLOY = "python:tests.fixtures.deploy_module"

asked: list[str] = []
approvals: list[str] = []


@pytest.fixture(autouse=True)
def scripted_channels():
    asked.clear()
    approvals.clear()

    async def answer(prompt, schema):
        asked.append(prompt)
        return "2" if "1." in prompt else "because I said so"

    async def approve(reason, detail):
        approvals.append(reason)
        return "prod" not in reason

    register_channel("scripted", lambda: CallbackChannel(answer, approve))
    register_channel("absent", UnreachableChannel)


@pytest.fixture
async def workspace(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add("human:kanishk?channel=scripted")
        await ws.add(DEPLOY)
        yield ws


async def test_a_person_gets_an_ordinary_descriptor(workspace):
    descriptor = workspace.registry.get("human/kanishk").descriptor
    assert descriptor.kind is Kind.HUMAN
    assert descriptor.runtime.residency is Residency.HUMAN
    assert descriptor.affordance("ask").latency_class is LatencyClass.HUMAN
    assert {a.name for a in descriptor.affordances} == {"ask", "approve", "choose"}


async def test_a_person_is_callable_like_anything_else(workspace):
    async with workspace.session() as s:
        answer = await s.result("human/kanishk", "ask", {"question": "why?"})
    assert answer == "because I said so"
    assert asked == ["why?"]


async def test_choose_accepts_a_number_or_the_option_text(workspace):
    async with workspace.session() as s:
        picked = await s.result(
            "human/kanishk", "choose", {"prompt": "which?", "options": ["red", "blue"]}
        )
    assert picked == "blue"


async def test_choose_rejects_an_answer_that_is_not_an_option(workspace):
    async def answer(prompt, schema):
        return "purple"

    register_channel("stubborn", lambda: CallbackChannel(answer, answer))
    await workspace.add("human:picky?channel=stubborn")

    async with workspace.session() as s:
        with pytest.raises(CallFailed):
            await s.result("human/picky", "choose", {"prompt": "?", "options": ["a", "b"]})


async def test_escalation_routes_to_the_person(workspace):
    async with workspace.session() as s:
        s.responder = route_to(s, "human/kanishk")
        assert await s.result("test/deploy", "deploy", {"target": "staging"}) == (
            "deployed to staging"
        )
        assert await s.result("test/deploy", "deploy", {"target": "prod"}) == "aborted"

    assert approvals == ["deploy to staging", "deploy to prod"]


async def test_escalation_shows_up_as_a_real_call_in_the_task_log(workspace):
    async with workspace.session() as s:
        s.responder = route_to(s, "human/kanishk")
        await s.result("test/deploy", "deploy", {"target": "staging"})
        called = {t.participant for t in s.router.tasks.values()}

    assert called == {"test/deploy", "human/kanishk"}


async def test_an_unreachable_person_falls_through_to_the_next(workspace):
    await workspace.add("human:away?channel=absent")

    async with workspace.session() as s:
        s.responder = first_available(s, "human/away", "human/kanishk")
        assert await s.result("test/deploy", "deploy", {"target": "staging"}) == (
            "deployed to staging"
        )
