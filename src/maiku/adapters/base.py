"""The adapter contract: one event discipline across calls, properties and subscriptions."""

import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from maiku.adapters.context import CallCancelled, CallContext
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.enums import AffordanceOperation
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.descriptor.validate import argument_errors
from maiku.wire.events import ArtifactWritten, Event, Failed, Finished, Started
from maiku.wire.health import Health
from maiku.wire.task import TaskState


class AdapterError(Exception):
    """Adapter failures the runtime can report without a traceback leaking to callers."""

    code = "adapter_error"
    retryable = False

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}

    def as_event(self) -> Failed:
        return Failed(
            code=self.code,
            message=str(self),
            retryable=self.retryable,
            detail=self.detail,
        )


class Unreachable(AdapterError):
    code = "unreachable"
    retryable = True


class UnknownAffordance(AdapterError):
    code = "unknown_affordance"


class InvalidArguments(AdapterError):
    code = "invalid_arguments"


class Adapter(ABC):
    scheme: ClassVar[str]
    version: ClassVar[str] = "0.0.1"

    _cached: ParticipantDescriptor | None = None

    @classmethod
    @abstractmethod
    async def open(cls, uri: ParticipantURI) -> "Adapter":
        """Connect to the underlying thing. May be expensive; called once per lifetime."""

    @abstractmethod
    async def describe(self) -> ParticipantDescriptor:
        """Derive the descriptor, ideally by introspection.

        Hand-authored descriptors are the failure mode that killed every service registry
        before this one. An adapter that cannot infer most of its own descriptor is an
        adapter that will not get used.
        """

    @abstractmethod
    def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        """Run one call, as a stream ending in exactly one terminal event."""

    def read_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        return _unsupported_operation(affordance, AffordanceOperation.READ)

    def write_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        return _unsupported_operation(affordance, AffordanceOperation.WRITE)

    def subscribe(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        return _unsupported_operation(affordance, AffordanceOperation.SUBSCRIBE)

    async def descriptor(self) -> ParticipantDescriptor:
        """describe(), cached for the life of this adapter instance.

        Descriptors are stable by construction, so the cache costs nothing and spares
        adapters that describe over a network a round trip on every call.
        """
        if self._cached is None:
            self._cached = await self.describe()
        return self._cached

    async def probe(self) -> Health:
        started = time.perf_counter()
        try:
            await self.describe()
        except Exception as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> "Adapter":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()


async def _unsupported_operation(
    affordance: str, operation: AffordanceOperation
) -> AsyncIterator[Event]:
    yield UnknownAffordance(
        f"{affordance!r} does not support the {operation.value} operation"
    ).as_event()


def _dispatch(
    adapter: Adapter,
    declared: Affordance,
    arguments: dict[str, Any],
    ctx: CallContext,
) -> AsyncIterator[Event]:
    """Select one adapter path after authorization and schema validation have succeeded.

    invoke/stream -> invoke
    property read -> read_property
    property write -> write_property
    event          -> subscribe
    """
    operation = declared.resolved_operation
    if operation is AffordanceOperation.READ:
        return adapter.read_property(declared.name, arguments, ctx)
    if operation is AffordanceOperation.WRITE:
        return adapter.write_property(declared.name, arguments, ctx)
    if operation is AffordanceOperation.SUBSCRIBE:
        return adapter.subscribe(declared.name, arguments, ctx)
    return adapter.invoke(declared.name, arguments, ctx)


async def guarded(
    adapter: Adapter,
    affordance: str,
    arguments: dict[str, Any],
    ctx: CallContext,
    *,
    declared: Affordance | None = None,
) -> AsyncIterator[Event]:
    """Wrap an operation so the stream invariant holds even when an adapter misbehaves.

    Also the merge point for events the adapter emits out of band via the context, so all
    stream discipline - ordering, sequencing, exactly one terminal event - lives here
    rather than being re-derived by every adapter author.
    """
    seq = 0
    terminated = False
    sentinel = object()
    announced: set[str] = set()

    def stamp(event: Event) -> Event:
        nonlocal seq
        event.seq = seq
        seq += 1
        return event

    async def pump(operation: Affordance) -> None:
        try:
            async for event in _dispatch(adapter, operation, arguments, ctx):
                ctx._outbox.put_nowait(event)
        except CallCancelled:
            ctx._outbox.put_nowait(Finished(state=TaskState.CANCELED))
        except AdapterError as exc:
            ctx._outbox.put_nowait(exc.as_event())
        except Exception as exc:
            ctx._outbox.put_nowait(Failed(message=f"{type(exc).__name__}: {exc}"))
        finally:
            ctx._outbox.put_nowait(sentinel)

    yield stamp(Started(participant=ctx.participant, affordance=affordance))

    try:
        operation = declared or (await adapter.descriptor()).affordance(affordance)
        if problems := argument_errors(operation, arguments):
            raise InvalidArguments(
                f"arguments for {affordance!r} are invalid", detail={"errors": problems}
            )
    except KeyError:
        yield stamp(UnknownAffordance(f"no affordance {affordance!r}").as_event())
        return
    except AdapterError as exc:
        yield stamp(exc.as_event())
        return

    worker = asyncio.create_task(pump(operation))
    try:
        while True:
            item = await ctx._outbox.get()
            if item is sentinel:
                break
            if terminated:
                continue
            if isinstance(item, ArtifactWritten):
                # The runtime announces every write; an adapter that also emits the event
                # is being helpful, not authoritative.
                if item.ref.digest in announced:
                    continue
                announced.add(item.ref.digest)
            terminated = type(item).terminal
            yield stamp(item)
    finally:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await worker

    if not terminated:
        yield stamp(Finished())
