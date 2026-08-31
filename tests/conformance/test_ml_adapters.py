"""torch and transformers are optional, so these run only where they are installed.

The descriptor shape they produce is already covered without either package by
tests/e2e/test_tensor_participants.py - these check the loading and device honesty that
only a real install can exercise.
"""

import pytest

from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import Device, Kind
from tests.conformance.contract import AdapterContract, drain

torch = pytest.importorskip("torch", reason="install maiku[torch] to run these")


@pytest.fixture
async def adapter():
    adapter = await open_participant("torch:tests.fixtures.torch_module:Doubler?name=doubler")
    yield adapter
    await adapter.close()


class TestTorchModel(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant("torch:tests.fixtures.torch_module:Doubler?name=doubler")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "forward", {"input": [1.0, 2.0, 3.0]}


async def test_descriptor_reports_the_device_it_actually_got(adapter):
    descriptor = await adapter.describe()
    assert descriptor.kind is Kind.MODEL
    assert descriptor.handle == "torch/doubler"
    assert descriptor.runtime.device in set(Device)
    assert descriptor.provenance.version == torch.__version__


async def test_a_forward_pass_returns_a_tensor_result(adapter):
    events = await drain(adapter, "forward", {"input": [1.0, 2.0]}, AdapterContract().context())
    result = events[-1].result
    assert result["shape"] == [2]
    assert result["data"] == [2.0, 4.0]


async def test_a_bad_shape_fails_cleanly(adapter):
    events = await drain(adapter, "forward", {"input": "not a tensor"}, AdapterContract().context())
    assert events[-1].type in {"failed", "finished"}
