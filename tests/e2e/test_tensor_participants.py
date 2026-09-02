"""The stress test: a participant whose currency is arrays and files, not text."""
import numpy as np
import pytest

from maiku.adapters.convert import TENSOR_MEDIA_TYPE
from maiku.descriptor.enums import Kind, LatencyClass
from maiku.descriptor.hints import artifact_arguments
from maiku.gateways.mcp_server import MCPGateway
from maiku.projections import a2a, mcp
from maiku.runtime.workspace import Workspace
from maiku.wire import tensors
from tests.conftest import everything

VISION = "python:tests.fixtures.vision_module"


@pytest.fixture
async def workspace(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(VISION)
        yield ws


@pytest.fixture
async def session(workspace):
    async with workspace.session() as s:
        yield s


async def test_a_classifier_is_an_ordinary_participant(workspace):
    descriptor = workspace.registry.get("local/vision").descriptor
    assert descriptor.kind is Kind.MODEL
    assert descriptor.affordance("logits").latency_class is LatencyClass.INSTANT
    assert {a.name for a in descriptor.affordances} == {
        "logits",
        "embed",
        "classify_file",
        "render",
    }


async def test_a_small_tensor_travels_inline(session):
    result = await session.result("local/vision", "logits", {"pixels": [1.0, 2.0, 3.0]})
    assert result["dtype"] == "float32"
    assert result["shape"] == [3]
    assert len(result["data"]) == 3
    assert "ref" not in result


async def test_a_large_tensor_spills_to_an_artifact(workspace, session):
    result = await session.result("local/vision", "embed", {"text": "hello"})

    assert result["shape"] == [64, 64]
    assert result["dtype"] == "float32"
    assert result.get("data") is None
    assert result["ref"]["media_type"] == TENSOR_MEDIA_TYPE

    raw = await workspace.artifacts.read(result["ref"]["digest"])
    restored = np.frombuffer(raw, dtype=np.float32).reshape(result["shape"])
    assert restored.shape == (64, 64)
    assert restored[0][0] == pytest.approx(sum(ord(c) for c in "hello"))


async def test_dtype_and_shape_are_reported_the_same_way_either_size(session):
    small = await session.result("local/vision", "logits", {"pixels": [1.0]})
    large = await session.result("local/vision", "embed", {"text": "x"})
    assert set(small) - {"data"} <= set(large) | {"data"}
    assert small["dtype"] and large["dtype"]
    assert small["shape"] and large["shape"]


async def test_a_participant_can_take_an_image_and_return_json(workspace, session):
    ref = await workspace.artifacts.write(b"\x89PNG" + b"x" * 7, media_type="image/png")
    verdict = await session.result(
        "local/vision", "classify_file", {"image": ref.digest}, readable={ref.digest}
    )
    assert verdict["label"] in {"cat", "dog", "neither"}
    assert 0 <= verdict["confidence"] <= 1


async def test_an_image_argument_is_declared_as_an_artifact(workspace):
    descriptor = workspace.registry.get("local/vision").descriptor
    schema = descriptor.affordance("classify_file").input_schema
    assert artifact_arguments(schema) == ["image"]


async def test_a_generated_image_comes_back_as_a_reference_not_bytes(workspace, session):
    digest = await session.result("local/vision", "render", {"width": 8, "height": 4})
    raw = await workspace.artifacts.read(digest)
    assert len(raw) == 8 * 4 * 3


async def test_a_non_chat_model_still_projects_to_both_ecosystems(workspace):
    descriptor = workspace.registry.get("local/vision").descriptor

    tools = {t["_meta"]["maiku/affordance"]: t for t in mcp.to_tools(descriptor, everything())}
    assert set(tools) == {"logits", "embed", "classify_file", "render"}
    assert tools["logits"]["annotations"]["readOnlyHint"] is True

    card = a2a.to_agent_card(descriptor, everything())
    assert {s["id"] for s in card["skills"]} == set(tools)


async def test_a_classifier_is_callable_from_an_mcp_client(session):
    gateway = MCPGateway(session)
    result = await gateway.call_tool("local_vision__logits", {"pixels": [1.0, 2.0]})
    assert result["isError"] is False
    assert result["structuredContent"]["shape"] == [3]


def test_array_detection_does_not_import_a_framework():
    assert tensors.is_array(np.zeros(3))
    assert not tensors.is_array("text")
    assert not tensors.is_array({"shape": 1})
    assert not tensors.is_array([1, 2, 3])
