"""The call path.

Everything a participant is allowed to do is decided here: the grant is checked before the
adapter is opened, arguments are rejected at the boundary, and a suspension mid-call is
routed back out to whoever can answer it.

Adapters stay ignorant of all of it. That is the point - an adapter author writes four
methods, and authorization, validation, artifact scoping and human escalation come free.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from maiku.adapters.base import Adapter, UnknownAffordance, guarded
from maiku.adapters.context import CallContext
from maiku.adapters.registry import open_participant
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.enums import Approval, SideEffect
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.runtime.artifacts import ArtifactStore, ScopedArtifacts
from maiku.runtime.grants import Denied, Grant, root_grant
from maiku.runtime.registry import Registry
from maiku.runtime.space import Space
from maiku.runtime.validation import check_arguments, result_warnings
from maiku.wire.events import (
    ArtifactWritten,
    Event,
    Failed,
    Finished,
    Log,
    NeedsApproval,
    NeedsInput,
)
from maiku.wire.parts import ArtifactRef
from maiku.wire.task import Task, TaskState, new_id

Responder = Callable[[NeedsInput | NeedsApproval], Awaitable[Any]]
Observer = Callable[[str, Event], None]


async def deny_everything(request: NeedsInput | NeedsApproval) -> Any:
    """The safe default. A runtime with nobody watching must not self-approve."""
    if isinstance(request, NeedsApproval):
        return False
    raise Denied("no responder is available to answer this request")


def needs_approval(descriptor: ParticipantDescriptor, side_effect: SideEffect) -> bool:
    policy = descriptor.permissions.approval
    if policy is Approval.ALWAYS:
        return True
    if policy is Approval.ON_SCOPE:
        return side_effect not in {SideEffect.NONE, SideEffect.READ}
    return False


@dataclass(slots=True)
class Call:
    """One in-flight invocation, resolved and authorized."""

    task: Task
    descriptor: ParticipantDescriptor
    affordance: Affordance
    arguments: dict[str, Any]
    grant: Grant
    caller: str | None = None
    readable: set[str] = field(default_factory=set)


class Router:
    def __init__(
        self,
        registry: Registry,
        store: ArtifactStore,
        space: Space,
        *,
        session_id: str,
        responder: Responder = deny_everything,
        observer: Observer | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.space = space
        self.session_id = session_id
        self.responder = responder
        self.observer = observer
        self.tasks: dict[str, Task] = {}
        self._adapters: dict[str, Adapter] = {}
        self._contexts: dict[str, CallContext] = {}

    async def adapter_for(self, handle: str) -> Adapter:
        if handle not in self._adapters:
            entry = self.registry.get(handle)
            self._adapters[handle] = await open_participant(entry.uri)
        return self._adapters[handle]

    def cancel(self, task_id: str) -> bool:
        ctx = self._contexts.get(task_id)
        if ctx is None:
            return False
        ctx.cancel()
        return True

    def answer(self, task_id: str, request_id: str, value: Any) -> bool:
        ctx = self._contexts.get(task_id)
        return bool(ctx and ctx.deliver(request_id, value))

    async def call(
        self,
        handle: str,
        affordance_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        caller: str | None = None,
        grant: Grant | None = None,
        readable: set[str] | None = None,
    ) -> AsyncIterator[Event]:
        arguments = dict(arguments or {})
        grant = grant or root_grant(caller or "user")

        entry = self.registry.get(handle)
        descriptor = entry.descriptor
        task = Task(
            id=new_id("task"),
            session_id=self.session_id,
            participant=handle,
            affordance=affordance_name,
            arguments=arguments,
        )
        self.tasks[task.id] = task

        try:
            affordance = descriptor.affordance(affordance_name)
        except KeyError as exc:
            yield self._terminate(task, Failed(code="unknown_affordance", message=str(exc)))
            return

        try:
            grant.check(
                handle,
                affordance_name,
                side_effect=affordance.side_effects,
                scopes=set(affordance.scopes),
            )
            check_arguments(affordance, arguments)
        except (Denied, UnknownAffordance) as exc:
            yield self._terminate(task, Failed(code="denied", message=str(exc)))
            return
        except Exception as exc:
            yield self._terminate(
                task,
                Failed(
                    code=getattr(exc, "code", "invalid_arguments"),
                    message=str(exc),
                    detail=getattr(exc, "detail", {}),
                ),
            )
            return

        if needs_approval(descriptor, affordance.side_effects):
            request = NeedsApproval(
                request_id=new_id("approval"),
                reason=f"{caller or 'user'} wants to call {handle}#{affordance_name}",
                side_effects=affordance.side_effects.value,
                detail={"arguments": arguments},
            )
            yield request
            if not await self.responder(request):
                yield self._terminate(
                    task, Failed(code="approval_denied", message="approval was refused")
                )
                return

        call = Call(
            task=task,
            descriptor=descriptor,
            affordance=affordance,
            arguments=arguments,
            grant=grant,
            caller=caller,
            readable=set(readable or ()),
        )
        async for event in self._run(call):
            yield event

    async def _run(self, call: Call) -> AsyncIterator[Event]:
        task, affordance = call.task, call.affordance
        produced: list[ArtifactRef] = []
        artifacts = ScopedArtifacts(
            self.store,
            readable=call.readable | set(call.grant.artifacts),
            on_write=produced.append,
        )
        ctx = CallContext(
            session_id=self.session_id,
            task_id=task.id,
            participant=call.descriptor.handle,
            caller=call.caller,
            artifacts=artifacts,
            scopes=frozenset(call.grant.scopes),
        )
        self._contexts[task.id] = ctx
        task.status.state = TaskState.WORKING

        pending: list[asyncio.Task] = []
        try:
            adapter = await self.adapter_for(call.descriptor.handle)
        except Exception as exc:
            yield self._terminate(
                task, Failed(code="unreachable", message=f"{type(exc).__name__}: {exc}")
            )
            return

        try:
            async for event in guarded(adapter, affordance.name, call.arguments, ctx):
                if isinstance(event, NeedsInput | NeedsApproval):
                    ctx.expect(event.request_id)
                    pending.append(asyncio.create_task(self._answer(ctx, event)))
                    task.status.state = (
                        TaskState.INPUT_REQUIRED
                        if isinstance(event, NeedsInput)
                        else TaskState.APPROVAL_REQUIRED
                    )
                elif isinstance(event, ArtifactWritten):
                    artifacts.grant(event.ref.digest)
                elif isinstance(event, Finished):
                    task.result = event.result
                    task.status.state = event.state
                    for warning in result_warnings(affordance, event.result):
                        yield Log(level="warning", message=f"result schema: {warning}")
                elif isinstance(event, Failed):
                    task.status.state = TaskState.FAILED
                    task.status.detail = event.message

                self._observe(event)
                yield event

            for ref in produced:
                task.metadata.setdefault("artifacts", []).append(ref.digest)
        finally:
            for job in pending:
                job.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*pending, return_exceptions=True)
            self._contexts.pop(task.id, None)

    async def _answer(self, ctx: CallContext, request: NeedsInput | NeedsApproval) -> None:
        try:
            ctx.deliver(request.request_id, await self.responder(request))
        except asyncio.CancelledError:
            raise
        except Exception:
            ctx.deliver(request.request_id, False if isinstance(request, NeedsApproval) else None)

    def _terminate(self, task: Task, event: Failed) -> Failed:
        task.status.state = TaskState.FAILED
        task.status.detail = event.message
        self._observe(event)
        return event

    def _observe(self, event: Event) -> None:
        if self.observer is not None:
            self.observer(self.session_id, event)

    async def close(self) -> None:
        for adapter in self._adapters.values():
            with contextlib.suppress(Exception):
                await adapter.close()
        self._adapters.clear()
