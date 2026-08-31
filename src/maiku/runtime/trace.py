"""Tracing, using the OpenTelemetry GenAI conventions where they fit.

Optional and silent by default: a local runtime should not require a collector, and an
import of opentelemetry that fails must not stop a call from running. When the SDK is
present, spans carry the GenAI attribute names the ecosystem already reads, so maiku traces
show up in an existing backend without bespoke dashboards.
"""

import contextlib
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from maiku.descriptor.participant import ParticipantDescriptor
from maiku.wire.events import Event, Failed, Usage

SPAN_NAME = "maiku.call"


@runtime_checkable
class Span(Protocol):
    def set(self, key: str, value: Any) -> None: ...

    def record(self, event: Event) -> None: ...


class NullSpan:
    def set(self, key: str, value: Any) -> None:
        return None

    def record(self, event: Event) -> None:
        return None


def call_attributes(
    descriptor: ParticipantDescriptor,
    affordance: str,
    *,
    session_id: str,
    task_id: str,
    caller: str | None,
) -> dict[str, Any]:
    attributes = {
        "gen_ai.operation.name": affordance,
        "gen_ai.system": descriptor.provenance.vendor or descriptor.provenance.adapter,
        "maiku.participant": descriptor.handle,
        "maiku.participant.id": descriptor.id,
        "maiku.kind": descriptor.kind.value,
        "maiku.residency": descriptor.runtime.residency.value,
        "maiku.session_id": session_id,
        "maiku.task_id": task_id,
    }
    if caller:
        attributes["maiku.caller"] = caller
    if descriptor.kind.value == "model":
        attributes["gen_ai.request.model"] = descriptor.display.name
    return attributes


class NullTracer:
    @contextlib.contextmanager
    def span(self, attributes: dict[str, Any]) -> Iterator[Span]:
        yield NullSpan()


class OTelTracer:
    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer

    @contextlib.contextmanager
    def span(self, attributes: dict[str, Any]) -> Iterator[Span]:
        """Started but not attached as the current span.

        A call is an async generator that suspends and resumes in different asyncio
        contexts, and `start_as_current_span` attaches a context token that cannot survive
        that - it raises on detach. Automatic parenting is the thing given up; a span per
        call that actually closes is worth more than one that nests and then throws.
        """
        span = self._tracer.start_span(SPAN_NAME, attributes=attributes)
        try:
            yield _OTelSpan(span)
        except Exception as exc:
            span.record_exception(exc)
            raise
        finally:
            span.end()


class _OTelSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set(self, key: str, value: Any) -> None:
        self._span.set_attribute(key, value)

    def record(self, event: Event) -> None:
        if isinstance(event, Usage):
            for key, value in {
                "gen_ai.usage.input_tokens": event.tokens_in,
                "gen_ai.usage.output_tokens": event.tokens_out,
                "maiku.usage.amount": event.amount,
                "maiku.usage.unit": event.unit,
            }.items():
                if value is not None:
                    self._span.set_attribute(key, value)
        elif isinstance(event, Failed):
            self._span.set_attribute("error.type", event.code)
            self._span.set_attribute("maiku.error.message", event.message)


def default_tracer() -> NullTracer | OTelTracer:
    try:
        from opentelemetry import trace
    except ImportError:
        return NullTracer()
    return OTelTracer(trace.get_tracer("maiku"))
