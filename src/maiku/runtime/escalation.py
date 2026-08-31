"""Sending a runtime escalation to a participant who can answer it.

The point of treating people as participants is that this needs no machinery: an approval
request becomes an ordinary call to `human/<name>#approve`, so it is grant-checked, traced
and logged exactly like a model invocation. Nothing about the escalation path is special.
"""

from typing import TYPE_CHECKING, Any

from maiku.runtime.router import Responder
from maiku.wire.events import NeedsApproval, NeedsInput

if TYPE_CHECKING:
    from maiku.runtime.session import Session


def route_to(session: "Session", handle: str, *, caller: str = "runtime") -> Responder:
    async def responder(request: NeedsInput | NeedsApproval) -> Any:
        if isinstance(request, NeedsApproval):
            return await session.result(
                handle,
                "approve",
                {"reason": request.reason, "detail": request.detail},
                caller=caller,
            )
        return await session.result(handle, "ask", {"question": request.prompt}, caller=caller)

    return responder


def first_available(session: "Session", *handles: str) -> Responder:
    """Try each candidate in turn, so an unreachable person does not stall the session."""

    async def responder(request: NeedsInput | NeedsApproval) -> Any:
        for handle in handles:
            try:
                return await route_to(session, handle)(request)
            except Exception:  # noqa: BLE001 - an unreachable answerer is not fatal
                continue
        return False if isinstance(request, NeedsApproval) else None

    return responder
