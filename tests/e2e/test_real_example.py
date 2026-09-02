"""The real example, exercised as far as the machine allows.
from tests.conftest import everything

The CNN half runs anywhere torch and trained weights are present. The LLM half needs a
llama.cpp server on :8081 and skips without one, because a demo that silently stubs the
model it claims to be testing is worse than a skipped test.
"""

import httpx
import pytest
from examples.real import cnn

from maiku.runtime.workspace import Workspace
from tests.conftest import everything

CNN_URI = "python:examples.real.participants"
LLM_URI = "openai:cassia?base=http://127.0.0.1:8081/v1"

torch = pytest.importorskip("torch")
weights = pytest.mark.skipif(
    not cnn.WEIGHTS.exists(), reason="run: uv run python -m examples.real.cnn"
)


def llama_is_up() -> bool:
    try:
        return httpx.get("http://127.0.0.1:8081/v1/models", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
async def session(tmp_path):
    with Workspace(tmp_path / "home") as ws:
        await ws.add(CNN_URI)
        async with ws.session() as s:
            yield s


@weights
async def test_the_trained_cnn_reads_real_mnist_digits(session):
    """Ten real test images, against their human-written labels."""
    correct = 0
    for index in range(10):
        digest = await session.result("local/digits", "sample_digit", {"index": index})
        verdict = await session.result("local/digits", "classify", {"image": digest})
        truth = await session.result("local/digits", "ground_truth", {"index": index})
        correct += verdict["digit"] == truth
        assert 0.0 <= verdict["confidence"] <= 1.0

    assert correct >= 9, f"a 98% model got {correct}/10 - something is wrong with the wiring"


@weights
async def test_the_cnn_projects_to_mcp_as_a_classifier(session):
    from maiku.projections import mcp

    descriptor = session.workspace.registry.get("local/digits").descriptor
    tools = {t["_meta"]["maiku/affordance"]: t for t in mcp.to_tools(descriptor, everything())}

    assert tools["classify"]["annotations"]["readOnlyHint"] is True
    assert tools["classify"]["inputSchema"]["required"] == ["image"]


@weights
@pytest.mark.skipif(not llama_is_up(), reason="no llama-server on :8081")
async def test_a_real_llm_delegates_to_the_real_cnn(tmp_path):
    from maiku.runtime.delegate import delegate

    with Workspace(tmp_path / "home") as ws:
        await ws.add(CNN_URI)
        await ws.add(LLM_URI)
        async with ws.session() as s:
            outcome = await delegate(
                s,
                "openai/cassia",
                "Identify the digit in MNIST test image number 42.",
                system=(
                    "You cannot see images. Call sample_digit for an image, then classify "
                    "to read it. Report the digit. Be brief."
                ),
                using=["openai/cassia", "local/digits"],
                max_turns=6,
            )

    assert "local/digits#classify" in outcome.delegated
    assert not outcome.exhausted
    assert "4" in outcome.answer
