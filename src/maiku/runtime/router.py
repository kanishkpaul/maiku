"""The call path.

Everything a participant is allowed to do is decided here: the grant is checked before the
adapter is opened, arguments are rejected at the boundary, and a suspension mid-call is
routed back out to whoever can answer it.

Adapters stay ignorant of all of it. That is the point: authorization, validation,
artifact scoping and human escalation come free on every operation path.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

from maiku.adapters.base import Adapter, guarded
from maiku.adapters.context import CallContext
from maiku.adapters.registry import open_participant
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.enums import Approval, SideEffect
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.descriptor.validate import argument_errors, result_errors
from maiku.runtime.artifacts import ArtifactStore, ScopedArtifacts
from maiku.runtime.grants import Denied, Grant, root_grant
from maiku.runtime.registry import Registry
from maiku.runtime.space import Space
from maiku.runtime.trace import call_attributes, default_tracer
from maiku.wire.events import (
    ArtifactWritten,
    Event,
    Failed,
    Finished,
    Log,
    NeedsApproval,
    NeedsInput,
)
from maiku.wire.parts import ArtifactRef, DataPart, FilePart, TextPart
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
        narrate: bool = True,
        share_artifacts: bool = True,
        tracer: Any = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.space = space
        self.session_id = session_id
        self.responder = responder
        self.observer = observer
        self.narrate = narrate
        self.share_artifacts = share_artifacts
        self.tracer = tracer or default_tracer()
        self.tasks: dict[str, Task] = {}
        self.produced: set[str] = set()
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

    def _admit(
        self,
        task: Task,
        descriptor: ParticipantDescriptor,
        arguments: dict[str, Any],
        caller: str | None,
        grant: Grant,
        readable: set[str] | None,
    ) -> Call | Failed:
        """Resolve, authorize and validate, before anything expensive happens.

        Everything here is decided without opening an adapter or waking a human, which is
        the point: a call that was never going to be allowed should cost nothing.
        """
        try:
            affordance = descriptor.affordance(task.affordance)
        except KeyError as exc:
            return self._terminate(
                task, Failed(code="unknown_affordance", message=str(exc)), caller
            )

        try:
            grant.check(
                descriptor.handle,
                affordance.name,
                side_effect=affordance.side_effects,
                scopes=set(affordance.scopes),
            )
        except Denied as exc:
            return self._terminate(task, Failed(code="denied", message=str(exc)), caller)

        if problems := argument_errors(affordance, arguments):
            return self._terminate(
                task,
                Failed(
                    code="invalid_arguments",
                    message=f"arguments for {affordance.name!r} are invalid",
                    detail={"errors": problems},
                ),
                caller,
            )

        return Call(
            task=task,
            descriptor=descriptor,
            affordance=affordance,
            arguments=arguments,
            grant=grant,
            caller=caller,
            readable=set(readable or ()),
        )

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
        descriptor = self.registry.get(handle).descriptor
        task = Task(
            id=new_id("task"),
            session_id=self.session_id,
            participant=handle,
            affordance=affordance_name,
            arguments=arguments,
        )
        self.tasks[task.id] = task

        admitted = self._admit(
            task, descriptor, arguments, caller, grant or root_grant(caller or "user"), readable
        )
        if isinstance(admitted, Failed):
            yield admitted
            return

        if needs_approval(descriptor, admitted.affordance.side_effects):
            request = NeedsApproval(
                request_id=new_id("approval"),
                reason=f"{caller or 'user'} wants to call {handle}#{affordance_name}",
                side_effects=admitted.affordance.side_effects.value,
                detail={"arguments": arguments},
            )
            self._absorb(admitted, request)
            self._observe(request)
            yield request
            if not await self.responder(request):
                yield self._terminate(
                    task,
                    Failed(code="approval_denied", message="approval was refused"),
                    caller,
                )
                return

        # Closed rather than abandoned: a caller that stops reading early must still run
        # the inner generator's cleanup, or adapters leak and spans never close.
        async with aclosing(self._run(admitted)) as stream:
            async for event in stream:
                yield event

    async def _run(self, call: Call) -> AsyncIterator[Event]:
        task, affordance = call.task, call.affordance
        produced: list[ArtifactRef] = []

        ctx = CallContext(
            session_id=self.session_id,
            task_id=task.id,
            participant=call.descriptor.handle,
            caller=call.caller,
            scopes=frozenset(call.grant.scopes),
        )

        def produced_artifact(ref: ArtifactRef) -> None:
            """Announce every write into the call's own stream.

            One source of truth: the space, the gateways and the CLI all learn about an
            artifact the same way, instead of each re-deriving it. An adapter that also
            emits the event is being helpful, and guarded() drops the duplicate.
            """
            produced.append(ref)
            self.produced.add(ref.digest)
            ctx.emit(ArtifactWritten(ref=ref))

        # A participant must be able to read what an earlier step in the same session
        # produced, or a pipeline cannot hand a file along - which is most of what a
        # pipeline is. The session is the sharing boundary; the grant still governs what
        # may be *done*. Two different axes, deliberately.
        ctx.artifacts = ScopedArtifacts(
            self.store,
            readable=(
                call.readable
                | set(call.grant.artifacts)
                | (self.produced if self.share_artifacts else set())
            ),
            on_write=produced_artifact,
        )
        self._contexts[task.id] = ctx
        task.status.state = TaskState.WORKING
        self._post(
            call.caller or "user",
            [DataPart(data=call.arguments)],
            mentions=[call.descriptor.handle],
            task=task,
        )

        pending: list[asyncio.Task] = []
        attributes = call_attributes(
            call.descriptor,
            affordance.name,
            session_id=self.session_id,
            task_id=task.id,
            caller=call.caller,
        )

        try:
            adapter = await self.adapter_for(call.descriptor.handle)
        except Exception as exc:
            yield self._terminate(
                task,
                Failed(code="unreachable", message=f"{type(exc).__name__}: {exc}"),
                call.caller,
            )
            return

        try:
            with self.tracer.span(attributes) as span:
                async for event in guarded(
                    adapter,
                    affordance.name,
                    call.arguments,
                    ctx,
                    declared=affordance,
                ):
                    span.record(event)
                    if isinstance(event, NeedsInput | NeedsApproval):
                        ctx.expect(event.request_id)
                        pending.append(asyncio.create_task(self._answer(ctx, event)))

                    self._absorb(call, event)
                    self._observe(event)
                    yield event

                    if isinstance(event, Finished):
                        for warning in result_errors(affordance, event.result):
                            yield Log(level="warning", message=f"result schema: {warning}")

                for ref in produced:
                    task.metadata.setdefault("artifacts", []).append(ref.digest)
        finally:
            for job in pending:
                job.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*pending, return_exceptions=True)
            self._contexts.pop(task.id, None)

    def _absorb(self, call: Call, event: Event) -> None:
        """Advance the task and record the event in the space. One place, one story."""
        task = call.task
        author, mentions = call.descriptor.handle, [call.caller] if call.caller else []

        if isinstance(event, NeedsInput):
            task.status.state = TaskState.INPUT_REQUIRED
        elif isinstance(event, NeedsApproval):
            task.status.state = TaskState.APPROVAL_REQUIRED
        elif isinstance(event, ArtifactWritten):
            self._post(author, [FilePart(ref=event.ref)], task=task)
        elif isinstance(event, Finished):
            task.result = event.result
            task.status.state = event.state
            self._post(author, [DataPart(data=event.result)], mentions=mentions, task=task)
        elif isinstance(event, Failed):
            task.status.state = TaskState.FAILED
            task.status.detail = event.message
            self._post(
                author,
                [TextPart(text=f"{event.code}: {event.message}")],
                mentions=mentions,
                task=task,
                metadata={"failed": True},
            )

    async def _answer(self, ctx: CallContext, request: NeedsInput | NeedsApproval) -> None:
        try:
            ctx.deliver(request.request_id, await self.responder(request))
        except asyncio.CancelledError:
            raise
        except Exception:
            ctx.deliver(request.request_id, False if isinstance(request, NeedsApproval) else None)

    def _terminate(self, task: Task, event: Failed, caller: str | None = None) -> Failed:
        task.status.state = TaskState.FAILED
        task.status.detail = event.message
        self._post(
            task.participant,
            [TextPart(text=f"{event.code}: {event.message}")],
            task=task,
            mentions=[caller] if caller else [],
            metadata={"failed": True},
        )
        self._observe(event)
        return event

    def _post(
        self,
        author: str,
        parts: list[Any],
        *,
        task: Task,
        mentions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record the call in the shared space, one thread per task.

        Without this the space is an empty room: a participant can only ever learn about
        work it was directly handed. Posting requests, results and produced artifacts is
        what lets one that was not part of the original plan notice relevant output.
        """
        if not self.narrate:
            return
        self.space.post(
            author,
            parts,
            mentions=mentions or [],
            thread_id=task.id,
            task_id=task.id,
            metadata=metadata or {},
        )

    def _observe(self, event: Event) -> None:
        if self.observer is not None:
            self.observer(self.session_id, event)

    async def close(self) -> None:
        for adapter in self._adapters.values():
            with contextlib.suppress(Exception):
                await adapter.close()
        self._adapters.clear()
