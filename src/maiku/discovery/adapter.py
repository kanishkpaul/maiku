"""`auto:<address>` — point maiku at an address and let the readers answer.

An adapter rather than a special case in the CLI, so everything downstream — `add`, `ls`,
`describe`, health — works on a discovered participant without knowing it was discovered.
"""

from collections.abc import AsyncIterator, Iterable
from typing import Any

from maiku.adapters.base import Adapter, AdapterError
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.discovery.assemble import Discovery, discover
from maiku.discovery.base import Address, Discoverer
from maiku.wire.events import Event


def default_discoverers() -> list[Discoverer]:
    """The registered readers. Precedence lives on each one, ordering lives in assemble."""
    from maiku.discovery.mcp import MCPDiscoverer
    from maiku.discovery.openapi import OpenAPIDiscoverer

    return [OpenAPIDiscoverer(), MCPDiscoverer()]


@register
class AutoAdapter(Adapter):
    scheme = "auto"

    def __init__(
        self, uri: ParticipantURI, discoverers: Iterable[Discoverer] | None = None
    ) -> None:
        self._uri = uri
        self._address = Address.parse(uri.target)
        self._discoverers = list(discoverers) if discoverers is not None else default_discoverers()
        self._found: Discovery | None = None

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "AutoAdapter":
        return cls(uri)

    def with_discoverers(self, discoverers: Iterable[Discoverer]) -> "AutoAdapter":
        return AutoAdapter(self._uri, discoverers)

    @property
    def address(self) -> Address:
        return self._address

    async def discovery(self) -> Discovery:
        if self._found is None:
            self._found = await discover(self._address, self._discoverers)
        return self._found

    async def describe(self) -> ParticipantDescriptor:
        return (await self.discovery()).descriptor

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        descriptor = await self.descriptor()
        binding = descriptor.binding_for(affordance)
        raise AdapterError(
            f"discovery describes {descriptor.handle} but does not route calls; "
            f"add {affordance!r} directly at {binding.scheme}:{binding.uri}"
        )
        yield  # unreachable: makes this an async generator, as the contract requires

    async def close(self) -> None:
        for discoverer in self._discoverers:
            if closer := getattr(discoverer, "close", None):
                await closer()
