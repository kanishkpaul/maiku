"""A session: who is in the room, what they may do, and what they said.

Sessions own the ephemeral half of the runtime - the space, the live adapters, and the
grant each participant is acting under. Nothing here is persisted; the workspace holds
what is worth keeping.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from typing import Any

from maiku.descriptor.enums import SideEffect
from maiku.runtime.grants import Grant, root_grant
from maiku.runtime.registry import Entry
from maiku.runtime.router import Observer, Responder, Router, deny_everything
from maiku.runtime.space import Space
from maiku.runtime.workspace import Workspace
from maiku.wire.events import Event, Failed, Finished
from maiku.wire.task import new_id


class CallFailed(RuntimeError):
    def __init__(self, event: Failed) -> None:
        super().__init__(f"{event.code}: {event.message}")
        self.event = event


class Session:
    def __init__(
        self,
        workspace: Workspace,
        *,
        session_id: str | None = None,
        owner: str = "user",
        responder: Responder = deny_everything,
        observer: Observer | None = None,
        share_artifacts: bool = True,
    ) -> None:
        self.workspace = workspace
        self.id = session_id or new_id("session")
        self.owner = owner
        self.space = Space(self.id)
        self.root_grant = root_grant(owner)
        self._grants: dict[str, Grant] = {}
        self.router = Router(
            workspace.registry,
            workspace.artifacts,
            self.space,
            session_id=self.id,
            responder=responder,
            observer=observer,
            share_artifacts=share_artifacts,
        )

    @property
    def responder(self) -> Responder:
        return self.router.responder

    @responder.setter
    def responder(self, responder: Responder) -> None:
        self.router.responder = responder

    def participants(self) -> list[Entry]:
        return self.workspace.registry.list()

    def grant(self, subject: str, **narrower: Any) -> Grant:
        """Issue a bounded grant to a participant acting on the owner's behalf."""
        issued = self.root_grant.attenuate(subject, **narrower)
        self._grants[subject] = issued
        return issued

    def grant_for(self, subject: str | None) -> Grant:
        if subject is None:
            return self.root_grant
        return self._grants.get(subject, self.root_grant)

    def call(
        self,
        handle: str,
        affordance: str,
        arguments: dict[str, Any] | None = None,
        *,
        caller: str | None = None,
        grant: Grant | None = None,
        readable: set[str] | None = None,
    ) -> AsyncIterator[Event]:
        """`grant` overrides the lookup for callers the session never issued one to.

        A gateway holds its client's grant directly; without this it would have to be
        registered under a subject first, and a subject the session did not recognise
        would quietly fall back to the owner's root grant.
        """
        return self.router.call(
            handle,
            affordance,
            arguments,
            caller=caller,
            grant=grant or self.grant_for(caller),
            readable=readable,
        )

    async def result(
        self,
        handle: str,
        affordance: str,
        arguments: dict[str, Any] | None = None,
        *,
        caller: str | None = None,
        readable: set[str] | None = None,
    ) -> Any:
        """Run a call to completion and hand back just the answer.

        Closed explicitly rather than abandoned on the early return: an async generator
        dropped mid-stream defers its finally blocks to garbage collection, which leaves
        adapter cleanup pending and trace spans open for an unbounded time.
        """
        async with aclosing(
            self.call(handle, affordance, arguments, caller=caller, readable=readable)
        ) as stream:
            async for event in stream:
                if isinstance(event, Failed):
                    raise CallFailed(event)
                if isinstance(event, Finished):
                    return event.result
        return None

    async def close(self) -> None:
        await self.router.close()

    async def __aenter__(self) -> "Session":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()


def approve_if(
    predicate: Callable[[Any], bool],
) -> Responder:
    """Build a responder that auto-approves only what the predicate allows."""

    async def responder(request: Any) -> Any:
        return predicate(request)

    return responder


def auto_approve_below(ceiling: SideEffect) -> Responder:
    """Approve calls whose blast radius stays under a threshold, escalate nothing else."""
    from maiku.descriptor.enums import SIDE_EFFECT_ORDER

    limit = SIDE_EFFECT_ORDER[ceiling]

    async def responder(request: Any) -> Any:
        effect = SideEffect(getattr(request, "side_effects", SideEffect.NONE))
        return SIDE_EFFECT_ORDER[effect] <= limit

    return responder


__all__ = [
    "CallFailed",
    "Session",
    "approve_if",
    "auto_approve_below",
]
