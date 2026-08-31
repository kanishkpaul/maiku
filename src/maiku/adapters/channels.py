"""How a question actually reaches a person.

The participant is the human; the channel is only the doorbell. Keeping them apart means
moving someone from a terminal prompt to Slack does not change what they are in the
runtime.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

Answer = Callable[[str, dict[str, Any]], Awaitable[Any]]


@runtime_checkable
class Channel(Protocol):
    name: str

    async def ask(self, prompt: str, input_schema: dict[str, Any]) -> Any: ...

    async def approve(self, reason: str, detail: dict[str, Any]) -> bool: ...


class CLIChannel:
    """Terminal prompts. Blocking reads go to a thread so the session keeps running."""

    name = "cli"

    async def ask(self, prompt: str, input_schema: dict[str, Any]) -> Any:
        answer = await asyncio.to_thread(input, f"\n[maiku] {prompt}\n> ")
        return _coerce(answer, input_schema)

    async def approve(self, reason: str, detail: dict[str, Any]) -> bool:
        rendered = json.dumps(detail, indent=2, default=str) if detail else ""
        answer = await asyncio.to_thread(
            input, f"\n[maiku] approve: {reason}\n{rendered}\n[y/N] > "
        )
        return answer.strip().lower() in {"y", "yes"}


class CallbackChannel:
    """A channel backed by a coroutine. Used for tests, and for any non-terminal front end."""

    name = "callback"

    def __init__(self, answer: Answer, approve: Callable[[str, dict], Awaitable[bool]]) -> None:
        self._answer = answer
        self._approve = approve

    async def ask(self, prompt: str, input_schema: dict[str, Any]) -> Any:
        return await self._answer(prompt, input_schema)

    async def approve(self, reason: str, detail: dict[str, Any]) -> bool:
        return await self._approve(reason, detail)


class UnreachableChannel:
    """Nobody is home.

    Both methods raise rather than returning a denial: "they said no" and "we could not
    reach them" are different facts, and a fallback chain that cannot tell them apart will
    stop at the first person who is asleep. The safe-default deny belongs to the runtime,
    not to the doorbell.
    """

    name = "unreachable"

    async def ask(self, prompt: str, input_schema: dict[str, Any]) -> Any:
        raise TimeoutError(f"nobody available to answer: {prompt}")

    async def approve(self, reason: str, detail: dict[str, Any]) -> bool:
        raise TimeoutError(f"nobody available to approve: {reason}")


CHANNELS: dict[str, Callable[[], Channel]] = {
    "cli": CLIChannel,
    "unreachable": UnreachableChannel,
}


def register_channel(name: str, factory: Callable[[], Channel]) -> None:
    CHANNELS[name] = factory


def channel_named(name: str) -> Channel:
    factory = CHANNELS.get(name)
    if factory is None:
        raise KeyError(f"unknown channel {name!r}; known: {', '.join(sorted(CHANNELS))}")
    return factory()


def _coerce(answer: str, input_schema: dict[str, Any]) -> Any:
    """Best-effort typing of a typed answer, falling back to the raw string."""
    expected = input_schema.get("type")
    if expected in {None, "string"}:
        return answer
    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        return answer
