"""Ingest an MCP server as a participant.

MCP's behavioural hints map onto maiku's side-effect ladder exactly, which is the whole
argument for the descriptor being a superset rather than a rival: adapting an MCP server
loses nothing, and the same participant then projects back out to A2A, which MCP cannot
express on its own.

Content blocks that are not text become artifacts. An MCP server returning a PNG should
hand the next participant a file reference, not a base64 string in a message.
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance
from maiku.adapters.context import CallContext
from maiku.adapters.jsonrpc import StdioClient
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Approval,
    Determinism,
    Kind,
    LatencyClass,
    Residency,
    SideEffect,
    Transport,
)
from maiku.descriptor.participant import (
    ArtifactPolicy,
    Display,
    IODefaults,
    ParticipantDescriptor,
    Permissions,
    Provenance,
    RuntimeInfo,
)
from maiku.wire.events import ArtifactWritten, Event, Finished, Log
from maiku.wire.health import Health

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "maiku", "version": "0.0.1"}


def side_effect_from(annotations: dict[str, Any]) -> SideEffect:
    """Invert the projection in maiku.projections.mcp, conservatively.

    Absent hints mean unknown, and unknown is treated as write rather than none: a tool
    that never said it was safe should not be assumed to be.
    """
    if annotations.get("destructiveHint"):
        return SideEffect.IRREVERSIBLE
    if annotations.get("openWorldHint"):
        return SideEffect.EXTERNAL
    if annotations.get("readOnlyHint"):
        return SideEffect.READ
    return SideEffect.WRITE


def to_affordance(tool: dict[str, Any]) -> Affordance:
    annotations = tool.get("annotations") or {}
    name = str(tool["name"]).lower().replace("-", "_").replace(".", "_")
    return Affordance(
        name=name,
        summary=(tool.get("title") or annotations.get("title") or tool["name"])[:200],
        description=tool.get("description") or "",
        kind=AffordanceKind.INVOKE,
        input_schema=tool.get("inputSchema") or {"type": "object", "properties": {}},
        output_schema=tool.get("outputSchema") or {},
        determinism=Determinism.SIDE_EFFECTING,
        latency_class=LatencyClass.SECONDS,
        idempotent=bool(annotations.get("idempotentHint")),
        side_effects=side_effect_from(annotations),
        tags=["mcp"],
    )


@register
class MCPAdapter(Adapter):
    scheme = "mcp"

    def __init__(self, uri: ParticipantURI) -> None:
        self._uri = uri
        self._client = StdioClient(uri.target, cwd=uri.param("cwd"))
        self._server: dict[str, Any] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._ready = False

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "MCPAdapter":
        adapter = cls(uri)
        await adapter._connect()
        return adapter

    async def _connect(self) -> None:
        if self._ready:
            return
        await self._client.start()
        result = await self._client.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
            timeout=float(self._uri.param("timeout", "30") or 30),
        )
        self._server = (result or {}).get("serverInfo") or {}
        await self._client.notify("notifications/initialized")

        listing = await self._client.request("tools/list")
        self._tools = {t["name"]: t for t in (listing or {}).get("tools") or []}
        if not self._tools:
            raise AdapterError(f"{self._uri.target!r} exposes no tools")
        self._ready = True

    @property
    def _name(self) -> str:
        return self._uri.param("name") or self._server.get("name") or "server"

    def _tool_for(self, affordance: str) -> dict[str, Any]:
        for tool in self._tools.values():
            if to_affordance(tool).name == affordance:
                return tool
        raise UnknownAffordance(f"{affordance!r} is not a tool on {self._name}")

    async def describe(self) -> ParticipantDescriptor:
        await self._connect()
        affordances = [to_affordance(tool) for tool in self._tools.values()]
        return ParticipantDescriptor(
            handle=f"mcp/{self._name.lower().replace(' ', '-')}",
            kind=Kind.TOOL,
            display=Display(
                name=self._server.get("title") or self._name,
                description=f"MCP server exposing {len(affordances)} tool(s)",
                tags=["mcp", "tools"],
            ),
            provenance=Provenance(
                vendor=self._name,
                version=self._server.get("version", ""),
                source_uri=self._uri.raw,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(
                residency=Residency.SUBPROCESS,
                host="localhost",
                max_concurrency=1,
            ),
            affordances=affordances,
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.STDIO,
                    uri=self._uri.raw,
                    config={"protocolVersion": PROTOCOL_VERSION},
                )
            ],
            io_defaults=IODefaults(
                input_modes=["application/json"],
                output_modes=["text/plain", "application/json"],
            ),
            artifacts=ArtifactPolicy(can_write=["image/*", "application/octet-stream"]),
            permissions=Permissions(
                side_effects=max(
                    (a.side_effects for a in affordances),
                    key=lambda e: list(SideEffect).index(e),
                    default=SideEffect.NONE,
                ),
                # An MCP server is usually someone else's code with a shell in it. Being
                # able to say "ask me before anything destructive" at adapt time is the
                # difference between using a third-party server and trusting one.
                approval=Approval(self._uri.param("approval", Approval.NEVER.value)),
            ),
        )

    async def probe(self) -> Health:
        if not self._client.running:
            return Health.down(self._client.stderr_tail or "process is not running")
        try:
            await self._client.request("tools/list", timeout=5.0)
        except Exception as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        return Health.up()

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        tool = self._tool_for(affordance)
        result = await self._client.request(
            "tools/call", {"name": tool["name"], "arguments": arguments}
        )
        result = result or {}

        texts: list[str] = []
        for block in result.get("content") or []:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif event := await self._store_block(block, ctx):
                yield event
            else:
                yield Log(level="warning", message=f"dropped {block.get('type')!r} block")

        if result.get("isError"):
            raise AdapterError("\n".join(texts) or f"{tool['name']} failed")

        yield Finished(result=result.get("structuredContent", "\n".join(texts)))

    async def _store_block(self, block: dict[str, Any], ctx: CallContext) -> Event | None:
        payload = block.get("data") or block.get("blob")
        if not payload or ctx.artifacts is None:
            return None
        ref = await ctx.artifacts.write(
            base64.b64decode(payload),
            media_type=block.get("mimeType", "application/octet-stream"),
            name=block.get("name"),
        )
        return ArtifactWritten(ref=ref)

    async def close(self) -> None:
        self._ready = False
        await self._client.close()
