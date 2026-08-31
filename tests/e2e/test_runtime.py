import pytest

from maiku.descriptor.enums import SideEffect
from maiku.runtime.grants import Capability
from maiku.runtime.session import CallFailed, auto_approve_below
from maiku.runtime.workspace import Workspace
from maiku.wire.events import Delta, NeedsApproval, NeedsInput

SAMPLE = "python:tests.fixtures.sample_module"
EFFECTS = "python:tests.fixtures.effects_module"
DEPLOY = "python:tests.fixtures.deploy_module"


@pytest.fixture
async def workspace(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        await ws.add(EFFECTS)
        await ws.add(DEPLOY)
        yield ws


@pytest.fixture
async def session(workspace):
    async with workspace.session() as s:
        yield s


async def test_adapting_registers_a_participant(workspace):
    entry = workspace.registry.get("test/sample")
    assert entry.uri == SAMPLE
    assert {a.name for a in entry.descriptor.affordances} >= {"score", "tokens"}


async def test_handle_override(tmp_path):
    with Workspace(tmp_path / "h") as ws:
        entry = await ws.add(SAMPLE, handle="mine/scorer")
        assert entry.descriptor.handle == "mine/scorer"
        assert ws.registry.get("mine/scorer")


async def test_call_returns_the_result(session):
    assert await session.result("test/sample", "score", {"text": "x" * 50}) == pytest.approx(1.0)


async def test_streaming_call_emits_deltas(session):
    events = [e async for e in session.call("test/sample", "tokens", {"text": "a b c"})]
    assert [e.part.text for e in events if isinstance(e, Delta)] == ["a", "b", "c"]
    assert events[-1].result == "abc"


async def test_invalid_arguments_are_rejected_at_the_boundary(session):
    with pytest.raises(CallFailed) as caught:
        await session.result("test/sample", "score", {"wrong": 1})
    assert caught.value.event.code == "invalid_arguments"


async def test_unknown_affordance_is_reported_not_raised(session):
    with pytest.raises(CallFailed) as caught:
        await session.result("test/sample", "nope")
    assert caught.value.event.code == "unknown_affordance"


async def test_probe_records_health(workspace):
    health = await workspace.refresh("test/sample")
    assert health.online
    assert workspace.registry.get("test/sample").health.online


async def test_search_finds_by_prose(workspace):
    assert [e.handle for e in workspace.registry.find("unsend")] == ["test/effects"]


async def test_irreversible_call_is_blocked_without_approval(session):
    events = [e async for e in session.call("test/effects", "publish", {"message": "hi"})]
    assert any(isinstance(e, NeedsApproval) for e in events)
    assert events[-1].code == "approval_denied"


async def test_approval_lets_it_through(workspace):
    async def approve(request):
        return True

    async with workspace.session(responder=approve) as s:
        assert await s.result("test/effects", "publish", {"message": "hi"}) == "published: hi"


async def test_auto_approval_respects_the_ceiling(workspace):
    async with workspace.session(responder=auto_approve_below(SideEffect.WRITE)) as s:
        assert await s.result("test/effects", "render", {"text": "abc"})
        with pytest.raises(CallFailed):
            await s.result("test/effects", "publish", {"message": "no"})


async def test_grant_narrows_what_a_caller_may_do(session):
    session.grant(
        "helper",
        capabilities=[Capability.parse("test/sample#score")],
        max_side_effect=SideEffect.READ,
    )
    assert await session.result("test/sample", "score", {"text": "hi"}, caller="helper")

    with pytest.raises(CallFailed) as caught:
        await session.result("test/effects", "publish", {"message": "x"}, caller="helper")
    assert caught.value.event.code == "denied"


async def test_a_participant_can_write_an_artifact(workspace):
    async def approve(request):
        return True

    async with workspace.session(responder=approve) as s:
        digest = await s.result("test/effects", "render", {"text": "hello world"})
    assert await workspace.artifacts.read(digest) == b"hello world"


async def test_artifacts_must_be_granted_to_be_read(workspace):
    ref = await workspace.artifacts.write(b"private", media_type="text/plain")

    async with workspace.session() as s:
        without = await s.result("test/effects", "summarise", {"digest": ref.digest})
        granted = await s.result(
            "test/effects", "summarise", {"digest": ref.digest}, readable={ref.digest}
        )
    assert without == "read 0 granted artifact(s)"
    assert granted == "read 1 granted artifact(s)"


async def test_a_participant_can_ask_and_be_answered(workspace):
    async def helpful(request):
        assert isinstance(request, NeedsInput | NeedsApproval)
        return "42"

    async with workspace.session(responder=helpful) as s:
        assert await s.result("test/effects", "consult", {"question": "why"}) == "they said: 42"


async def test_context_injection_stays_out_of_the_schema(workspace):
    descriptor = workspace.registry.get("test/effects").descriptor
    assert "ctx" not in descriptor.affordance("render").input_schema["properties"]
    assert descriptor.affordance("render").input_schema["required"] == ["text"]


async def test_mid_call_approval_can_abort(workspace):
    async def refuse(request):
        return False

    async with workspace.session(responder=refuse) as s:
        assert await s.result("test/deploy", "deploy", {"target": "prod"}) == "aborted"


async def test_mid_call_approval_can_proceed(workspace):
    async def allow(request):
        assert request.side_effects == "irreversible"
        assert "prod" in request.reason
        return True

    async with workspace.session(responder=allow) as s:
        assert await s.result("test/deploy", "deploy", {"target": "prod"}) == "deployed to prod"


async def test_a_silent_runtime_never_self_approves(workspace):
    async with workspace.session() as s:
        assert await s.result("test/deploy", "deploy", {"target": "prod"}) == "aborted"


async def test_escalation_appears_in_the_event_stream(workspace):
    async def allow(request):
        return True

    async with workspace.session(responder=allow) as s:
        events = [e async for e in s.call("test/deploy", "deploy", {"target": "prod"})]

    assert any(isinstance(e, NeedsApproval) for e in events)
    assert [e.seq for e in events] == list(range(len(events)))


async def test_a_read_only_affordance_needs_nobody(workspace):
    async with workspace.session() as s:
        assert await s.result("test/deploy", "dry_run", {"target": "prod"}) == (
            "would deploy to prod"
        )


async def test_stopping_early_cleans_up_when_the_caller_closes_the_stream(workspace):
    """`async for` plus `break` does not close a generator - only the caller can.

    Session.result and the CLI do this for you; a caller driving session.call() by hand has
    to, and this is what it looks like.
    """
    from contextlib import aclosing

    seen = []
    async with workspace.session() as s:
        async with aclosing(s.call("test/sample", "tokens", {"text": "a b c d e"})) as stream:
            async for event in stream:
                if isinstance(event, Delta):
                    seen.append(event)
                    break

        task = next(t for t in s.router.tasks.values() if t.affordance == "tokens")
        assert task.id not in s.router._contexts

    assert len(seen) == 1


async def test_result_cleans_up_after_itself(workspace):
    async with workspace.session() as s:
        await s.result("test/sample", "tokens", {"text": "a b"})
        assert s.router._contexts == {}
