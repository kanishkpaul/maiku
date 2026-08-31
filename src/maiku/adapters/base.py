"""The adapter contract: four methods, and everything in the world fits behind them."""

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from maiku.adapters.context import CallCancelled, CallContext
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.wire.events import Event, Failed, Finished, Started
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

    @classmethod
    def can_handle(cls, uri: ParticipantURI) -> bool:
        return uri.scheme == cls.scheme

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


async def guarded(
    adapter: Adapter, affordance: str, arguments: dict[str, Any], ctx: CallContext
) -> AsyncIterator[Event]:
    """Wrap `invoke` so the stream invariant holds even when an adapter misbehaves.

    Adapters are third-party code. Enforcing "one terminal event, last" here rather than
    trusting each author is the difference between a contract and a convention.
    """
    seq = 0
    terminated = False

    def stamp(event: Event) -> Event:
        nonlocal seq
        event.seq = seq
        seq += 1
        return event

    yield stamp(Started(participant=ctx.participant, affordance=affordance))
    try:
        async for event in adapter.invoke(affordance, arguments, ctx):
            if terminated:
                continue
            terminated = type(event).terminal
            yield stamp(event)
    except CallCancelled:
        if not terminated:
            terminated = True
            yield stamp(Finished(state=TaskState.CANCELED))
    except AdapterError as exc:
        if not terminated:
            terminated = True
            yield stamp(exc.as_event())
    except Exception as exc:
        if not terminated:
            terminated = True
            yield stamp(Failed(message=f"{type(exc).__name__}: {exc}"))

    if not terminated:
        yield stamp(Finished())
