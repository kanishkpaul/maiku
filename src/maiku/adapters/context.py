"""What an adapter is handed at call time."""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from maiku.wire.events import Event, NeedsApproval, NeedsInput
from maiku.wire.parts import ArtifactRef
from maiku.wire.task import new_id


@runtime_checkable
class ArtifactIO(Protocol):
    """The slice of the artifact store an adapter is allowed to see.

    Structural, not inherited, so `maiku.adapters` never has to import `maiku.runtime`.
    """

    async def read(self, digest: str) -> bytes: ...

    async def path(self, digest: str) -> Path: ...

    async def write(
        self, data: bytes | Path, media_type: str = ..., name: str | None = ...
    ) -> ArtifactRef: ...


class CallCancelled(Exception):
    pass


class ResponseTimeout(Exception):
    pass


@dataclass
class CallContext:
    """Per-call state, including the channel that makes suspension work.

    An adapter that needs a human yields `NeedsInput` and then awaits `response()`. The
    router fulfils it with `deliver()`. That round trip inside one async generator is what
    lets a person participate without every adapter growing its own resume protocol.
    """

    session_id: str
    task_id: str
    participant: str
    caller: str | None = None
    artifacts: ArtifactIO | None = None
    scopes: frozenset[str] = frozenset()
    deadline: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    _cancelled: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _pending: dict[str, asyncio.Future] = field(default_factory=dict, repr=False)
    _outbox: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(CallCancelled(self.task_id))

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CallCancelled(self.task_id)

    async def wait_cancelled(self) -> None:
        """Wait without polling so a quiet long-lived device stream can still stop promptly."""
        await self._cancelled.wait()

    @property
    def remaining(self) -> float | None:
        return None if self.deadline is None else max(0.0, self.deadline - time.time())

    def expect(self, request_id: str) -> None:
        """Open a slot before yielding the event, so a fast reply cannot be missed."""
        self._pending.setdefault(request_id, asyncio.get_running_loop().create_future())

    async def response(self, request_id: str, timeout: float | None = None) -> Any:
        self.expect(request_id)
        future = self._pending[request_id]
        budget = timeout if timeout is not None else self.remaining
        try:
            return await asyncio.wait_for(future, timeout=budget)
        except TimeoutError as exc:
            raise ResponseTimeout(request_id) from exc
        finally:
            self._pending.pop(request_id, None)

    def deliver(self, request_id: str, value: Any) -> bool:
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(value)
        return True

    def emit(self, event: Event) -> None:
        """Push an event into the call's stream from outside the adapter's generator.

        Without this, only an adapter written as a generator could report progress or ask a
        question - which would exclude every plain function, and plain functions are most
        of what people want to adapt.
        """
        self._outbox.put_nowait(event)

    async def ask(
        self,
        prompt: str,
        input_schema: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Ask whoever is watching this session, and block until they answer."""
        request = NeedsInput(
            request_id=new_id("ask"),
            prompt=prompt,
            input_schema=input_schema or {},
        )
        self.expect(request.request_id)
        self.emit(request)
        return await self.response(request.request_id, timeout)

    async def approve(
        self,
        reason: str,
        side_effects: str = "none",
        detail: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Request permission mid-call. Denial is the default if nobody answers."""
        request = NeedsApproval(
            request_id=new_id("approval"),
            reason=reason,
            side_effects=side_effects,
            detail=detail or {},
        )
        self.expect(request.request_id)
        self.emit(request)
        try:
            return bool(await self.response(request.request_id, timeout))
        except ResponseTimeout:
            return False

    def requires(self, scope: str) -> bool:
        return scope in self.scopes
