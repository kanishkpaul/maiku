"""Read an address that speaks MCP over HTTP.

The tool-to-affordance derivation is `adapters.mcp_client.to_affordance` and is not
repeated here — a second copy would drift, and the two would disagree about the same
server. Only the transport is new: `adapters.mcp_client` speaks stdio to a subprocess and
cannot answer for an address, so this module carries the small Streamable HTTP client that
an address needs.
"""

import json
from typing import Any

from maiku.adapters.mcp_client import CLIENT_INFO, PROTOCOL_VERSION, to_affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import Kind, Transport
from maiku.descriptor.participant import Display, Provenance
from maiku.discovery.base import Address, Attempt, NotReadable, Reading

# Where MCP endpoints sit in practice: the conventional path, then the address itself.
ENDPOINT_PATHS = ("/mcp", "")
ACCEPT = "application/json, text/event-stream"
SESSION_HEADER = "Mcp-Session-Id"


class MCPDiscoverer:
    name = "mcp"
    precedence = 20

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        # One handshake serves both `applies` and `read`.
        self._found: dict[str, tuple[str, dict[str, Any], list[dict[str, Any]]]] = {}
        self._missed: dict[str, list[Attempt]] = {}

    async def applies(self, address: Address) -> bool:
        return await self._locate(address) is not None

    def attempted(self, address: Address) -> list[Attempt]:
        return self._missed.get(address.url, [])

    async def read(self, address: Address) -> Reading:
        located = await self._locate(address)
        if located is None:
            raise NotReadable(self.name, self._missed.get(address.url, []))

        endpoint, server, tools = located
        return Reading(
            source=self.name,
            affordances=[to_affordance(tool) for tool in tools],
            binding=Binding(
                scheme=self.name,
                transport=Transport.HTTP,
                uri=endpoint,
                config={"protocolVersion": PROTOCOL_VERSION},
            ),
            kind=Kind.TOOL,
            display=Display(
                name=server.get("title") or server.get("name") or address.slug,
                description=f"MCP server exposing {len(tools)} tool(s)",
                tags=["mcp", "tools"],
            ),
            provenance=Provenance(
                vendor=server.get("name", ""), version=server.get("version", "")
            ),
            attempts=(Attempt(endpoint, "read"),),
        )

    def candidates(self, address: Address) -> list[str]:
        return [address.join(path) if path else address.url for path in ENDPOINT_PATHS]

    async def _locate(
        self, address: Address
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]] | None:
        if (cached := self._found.get(address.url)) is not None:
            return cached

        attempts: list[Attempt] = []
        for endpoint in self.candidates(address):
            found, outcome = await self._handshake(endpoint)
            attempts.append(Attempt(endpoint, outcome))
            if found is not None:
                self._found[address.url] = (endpoint, *found)
                return self._found[address.url]

        self._missed[address.url] = attempts
        return None

    async def _handshake(
        self, endpoint: str
    ) -> tuple[tuple[dict[str, Any], list[dict[str, Any]]] | None, str]:
        initialised, outcome, session = await self._rpc(
            endpoint,
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        if initialised is None:
            return None, outcome
        if not initialised.get("protocolVersion"):
            return None, "answered JSON-RPC but declared no protocolVersion"

        listing, outcome, _ = await self._rpc(endpoint, "tools/list", session=session)
        if listing is None:
            return None, f"initialized, then tools/list {outcome}"

        tools = listing.get("tools") or []
        if not tools:
            return None, "initialized, but exposes no tools"
        return (initialised.get("serverInfo") or {}, tools), "read"

    async def _rpc(
        self,
        endpoint: str,
        method: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)

        headers = {"Content-Type": "application/json", "Accept": ACCEPT}
        if session:
            headers[SESSION_HEADER] = session

        try:
            response = await self._client.post(
                endpoint,
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
        except httpx.HTTPError as exc:
            return None, f"{type(exc).__name__}: {exc}", None

        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}", None

        payload = _decode(response)
        if payload is None:
            return None, "response is not JSON-RPC", None
        if "error" in payload:
            return None, f"JSON-RPC error {payload['error']}", None
        return payload.get("result") or {}, "read", response.headers.get(SESSION_HEADER)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


def _decode(response: Any) -> dict[str, Any] | None:
    """Streamable HTTP may answer as JSON or as a one-message SSE stream."""
    body = response.text
    if "text/event-stream" in response.headers.get("content-type", ""):
        body = next(
            (line[5:] for line in body.splitlines() if line.startswith("data:")),
            "",
        )
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("jsonrpc") == "2.0" else None
