import pytest

from maiku.adapters.registry import open_participant
from tests.conformance.contract import AdapterContract


class TestTensorParticipant(AdapterContract):
    """A model whose currency is arrays clears the same bar as one whose currency is text."""

    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant("python:tests.fixtures.vision_module")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "logits", {"pixels": [1.0, 2.0, 3.0]}
