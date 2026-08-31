"""What the shared space actually records, and what a participant can learn from it."""

import pytest

from maiku.runtime.session import CallFailed
from maiku.runtime.workspace import Workspace
from maiku.wire.parts import DataPart, FilePart

VISION = "python:tests.fixtures.vision_module"
SAMPLE = "python:tests.fixtures.sample_module"


@pytest.fixture
async def session(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(VISION)
        await ws.add(SAMPLE)
        async with ws.session() as s:
            yield s


async def test_a_call_leaves_a_request_and_a_result(session):
    await session.result("test/sample", "fetch", {"key": "abc"}, caller="planner")
    posts = session.space.history()

    assert [p.author for p in posts] == ["planner", "test/sample"]
    assert posts[0].mentions == ["test/sample"]
    assert posts[0].parts[0].data == {"key": "abc"}
    assert posts[1].parts[0].data == {"key": "abc", "value": "ABC"}
    assert posts[1].mentions == ["planner"]


async def test_one_thread_per_task(session):
    await session.result("test/sample", "fetch", {"key": "a"})
    await session.result("test/sample", "fetch", {"key": "b"})
    assert len(session.space.threads()) == 2
    assert len({p.task_id for p in session.space.history()}) == 2


async def test_a_produced_artifact_is_announced(session):
    await session.result("local/vision", "render", {"width": 4, "height": 2})
    files = [p for p in session.space.history() if isinstance(p.parts[0], FilePart)]

    assert len(files) == 1
    assert files[0].author == "local/vision"
    assert files[0].parts[0].ref.media_type == "image/x-raw"


async def test_a_failure_is_recorded_not_silently_dropped(session):
    with pytest.raises(CallFailed):
        await session.result("test/sample", "fetch", {"wrong": 1}, caller="planner")

    failures = [p for p in session.space.history() if p.metadata.get("failed")]
    assert len(failures) == 1
    assert "invalid_arguments" in failures[0].text


async def test_a_bystander_learns_about_work_it_was_not_handed(session):
    """The point of a blackboard: nobody had to tell this subscriber anything."""
    with session.space.subscribe("local/vision") as bystander:
        await session.result("local/vision", "logits", {"pixels": [1.0, 2.0]}, caller="planner")
        request = await bystander.next(timeout=1)

    assert request.author == "planner"
    assert isinstance(request.parts[0], DataPart)


async def test_narration_can_be_turned_off(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(SAMPLE)
        async with ws.session() as s:
            s.router.narrate = False
            await s.result("test/sample", "fetch", {"key": "a"})
            assert len(s.space) == 0


async def test_an_artifact_is_announced_once_even_when_the_adapter_also_emits_it(tmp_path):
    """MCP writes through the store and then emits the event; only one post should appear."""
    import sys

    with Workspace(tmp_path / "home") as ws:
        await ws.add(f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py")
        async with ws.session() as s:
            await s.result("mcp/fixture", "render_chart", {"title": "q4"})
            files = [p for p in s.space.history() if isinstance(p.parts[0], FilePart)]

    assert len(files) == 1
