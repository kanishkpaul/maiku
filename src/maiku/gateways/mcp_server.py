"""Serve maiku participants to any MCP client.

This is the direction that makes maiku useful on day one with nobody else using it: adapt a
PyTorch model, a Python function or a person, and Claude Code can call it as a tool. USB
has a host side and a device side; ingest without egress is only half an adapter.
"""

import asyncio
import json
import sys
from typing import Any

from maiku.projections.mcp import to_tools
from maiku.projections.naming import handle_slug, unflatten
from maiku.runtime.session import Session
from maiku.wire.events import ArtifactWritten, Failed, Finished, Log

PROTOCOL_VERSION = "2025-06-18"
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


class MCPGateway:
    def __init__(self, session: Session, name: str = "maiku", version: str = "0.0.1") -> None:
        self.session = session
        self.name = name
        self.version = version

    def _routes(self) -> dict[str, tuple[str, str]]:
        """Flattened tool name to (handle, affordance).

        Rebuilt per listing rather than cached, so a participant adapted mid-session shows
        up without a restart.
        """
        routes = {}
        for entry in self.session.participants():
            for affordance in entry.descriptor.affordances:
                slug = handle_slug(entry.descriptor.handle)
                routes[f"{slug}__{affordance.name}"] = (entry.handle, affordance.name)
        return routes

    def tools(self) -> list[dict[str, Any]]:
        return [
            tool for entry in self.session.participants() for tool in to_tools(entry.descriptor)
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        route = self._routes().get(name)
        if route is None:
            try:
                slug, _ = unflatten(name)
            except ValueError:
                return _error(f"unknown tool {name!r}")
            return _error(f"unknown tool {name!r}: no participant matching {slug!r}")

        handle, affordance = route
        blocks: list[dict[str, Any]] = []
        result: Any = None
        failure: Failed | None = None

        async for event in self.session.call(handle, affordance, arguments):
            if isinstance(event, ArtifactWritten):
                blocks.append(
                    {
                        "type": "resource_link",
                        "uri": f"maiku://artifact/{event.ref.digest}",
                        "name": event.ref.name or event.ref.digest,
                        "mimeType": event.ref.media_type,
                    }
                )
            elif isinstance(event, Log) and event.level in {"warning", "error"}:
                blocks.append({"type": "text", "text": f"[{event.level}] {event.message}"})
            elif isinstance(event, Finished):
                result = event.result
            elif isinstance(event, Failed):
                failure = event

        if failure is not None:
            return _error(f"{failure.code}: {failure.message}")

        blocks.insert(0, {"type": "text", "text": _render(result)})
        payload: dict[str, Any] = {"content": blocks, "isError": False}
        if isinstance(result, dict):
            payload["structuredContent"] = result
        return payload

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params") or {}

        if message_id is None:
            return None  # a notification; nothing to answer

        try:
            result = await self._dispatch(method, params)
        except LookupError:
            return _rpc_error(message_id, METHOD_NOT_FOUND, f"no such method: {method}")
        except Exception as exc:
            return _rpc_error(message_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    async def _dispatch(self, method: str | None, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {
                    "name": self.name,
                    "title": "maiku participants",
                    "version": self.version,
                },
            }
        if method == "tools/list":
            return {"tools": self.tools()}
        if method == "tools/call":
            return await self.call_tool(params["name"], params.get("arguments") or {})
        if method == "ping":
            return {}
        raise LookupError(method)

    async def serve_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while line := await loop.run_in_executor(None, sys.stdin.readline):
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (response := await self.handle(message)) is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def _render(result: Any) -> str:
    if isinstance(result, str):
        return result
    if result is None:
        return ""
    return json.dumps(result, indent=2, default=str)


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _rpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
