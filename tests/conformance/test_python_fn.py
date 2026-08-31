import pytest

from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import AffordanceKind, Determinism
from tests.conformance.contract import AdapterContract, drain


class TestPythonModule(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant("python:tests.fixtures.sample_module")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "score", {"text": "hello"}


class TestPythonFunction(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant("python:tests.fixtures.sample_module:fetch")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "fetch", {"key": "abc"}


async def module_adapter():
    return await open_participant("python:tests.fixtures.sample_module")


async def test_module_exposes_every_public_callable():
    descriptor = await (await module_adapter()).describe()
    assert {a.name for a in descriptor.affordances} == {"score", "fetch", "tokens", "narrate"}


async def test_docstring_splits_into_summary_and_description():
    descriptor = await (await module_adapter()).describe()
    score = descriptor.affordance("score")
    assert score.summary == "Score a string."
    assert "belongs in the description" in score.description


async def test_signature_becomes_input_schema():
    descriptor = await (await module_adapter()).describe()
    schema = descriptor.affordance("score").input_schema
    assert schema["required"] == ["text"]
    assert schema["properties"]["threshold"]["default"] == 0.5


async def test_generators_are_detected_as_streams():
    descriptor = await (await module_adapter()).describe()
    assert descriptor.affordance("tokens").kind is AffordanceKind.STREAM
    assert descriptor.affordance("narrate").kind is AffordanceKind.STREAM
    assert descriptor.affordance("score").kind is AffordanceKind.INVOKE


async def test_decorator_overrides_inference():
    descriptor = await (await module_adapter()).describe()
    assert descriptor.affordance("tokens").determinism is Determinism.STOCHASTIC
    assert descriptor.affordance("score").determinism is Determinism.DETERMINISTIC
    assert descriptor.handle == "test/sample"
    assert descriptor.display.tags == ["testing"]


async def test_sync_call_returns_the_value():
    adapter = await module_adapter()
    events = await drain(adapter, "score", {"text": "x" * 50}, AdapterContract().context())
    assert events[-1].result == pytest.approx(1.0)


async def test_stream_emits_deltas_and_collapses_text():
    adapter = await module_adapter()
    events = await drain(adapter, "tokens", {"text": "a b c"}, AdapterContract().context())
    deltas = [e for e in events if e.type == "delta"]
    assert [d.part.text for d in deltas] == ["a", "b", "c"]
    assert events[-1].result == "abc"


async def test_async_stream_works():
    adapter = await module_adapter()
    events = await drain(adapter, "narrate", {"count": 3}, AdapterContract().context())
    assert events[-1].result == "3 2 1 "


async def test_private_callables_are_not_exposed():
    descriptor = await (await module_adapter()).describe()
    assert "_private" not in {a.name for a in descriptor.affordances}
