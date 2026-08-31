import pytest

from maiku.adapters.channels import CallbackChannel, register_channel
from maiku.adapters.registry import open_participant
from tests.conformance.contract import AdapterContract


class TestHuman(AdapterContract):
    """A person has to clear the same bar as a GPU. That is the whole thesis."""

    @pytest.fixture
    async def adapter(self):
        async def answer(prompt, schema):
            return "ok"

        async def approve(reason, detail):
            return True

        register_channel("conformance", lambda: CallbackChannel(answer, approve))
        adapter = await open_participant("human:tester?channel=conformance")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "ask", {"question": "are you there?"}
