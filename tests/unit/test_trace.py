import pytest

from maiku.runtime.trace import NullTracer, OTelTracer, call_attributes, default_tracer
from maiku.wire.events import Failed, Usage
from tests.conftest import make_descriptor


def test_attributes_follow_the_genai_conventions(descriptor):
    attributes = call_attributes(
        descriptor, "classify", session_id="s1", task_id="t1", caller="planner"
    )
    assert attributes["gen_ai.operation.name"] == "classify"
    assert attributes["gen_ai.system"] == "hf"
    assert attributes["gen_ai.request.model"] == "Sentiment"
    assert attributes["maiku.participant"] == descriptor.handle
    assert attributes["maiku.caller"] == "planner"


def test_non_models_do_not_claim_a_model_name():
    from maiku.descriptor.enums import Kind

    attributes = call_attributes(
        make_descriptor(kind=Kind.TOOL), "classify", session_id="s", task_id="t", caller=None
    )
    assert "gen_ai.request.model" not in attributes
    assert "maiku.caller" not in attributes


def test_the_null_tracer_is_inert():
    with NullTracer().span({"a": 1}) as span:
        span.set("b", 2)
        span.record(Usage(tokens_in=1))


def test_default_tracer_uses_otel_when_it_is_installed():
    pytest.importorskip("opentelemetry")
    assert isinstance(default_tracer(), OTelTracer)


async def test_a_real_span_is_recorded_for_every_call(tmp_path):
    trace = pytest.importorskip("opentelemetry.trace")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from maiku.runtime.workspace import Workspace

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with Workspace(tmp_path / "home") as ws:
        await ws.add("python:tests.fixtures.sample_module")
        async with ws.session() as session:
            session.router.tracer = OTelTracer(trace.get_tracer("test", tracer_provider=provider))
            await session.result("test/sample", "fetch", {"key": "abc"}, caller="planner")

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["maiku.call"]
    assert spans[0].attributes["gen_ai.operation.name"] == "fetch"
    assert spans[0].attributes["maiku.participant"] == "test/sample"
    assert spans[0].attributes["maiku.caller"] == "planner"


def test_usage_and_failure_land_on_the_span():
    recorded = {}

    class FakeSpan:
        def set_attribute(self, key, value):
            recorded[key] = value

    from maiku.runtime.trace import _OTelSpan

    span = _OTelSpan(FakeSpan())
    span.record(Usage(tokens_in=7, tokens_out=3, unit="token", amount=10))
    span.record(Failed(code="denied", message="nope"))

    assert recorded["gen_ai.usage.input_tokens"] == 7
    assert recorded["gen_ai.usage.output_tokens"] == 3
    assert recorded["error.type"] == "denied"
