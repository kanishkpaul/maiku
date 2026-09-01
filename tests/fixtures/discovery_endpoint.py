"""One address that publishes both an OpenAPI document and an MCP endpoint.

Two readers answering for a single address is what forces assembly and precedence to be
real rather than assumed, so the fixture serves both from one host — and both declare a
`classify` tool with different schemas, so the conflict path is exercised too.
"""

from typing import Any

import httpx

HOST = "http://device.local"

TEXT_INPUT = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
BYTES_INPUT = {
    "type": "object",
    "properties": {"payload": {"type": "string"}},
    "required": ["payload"],
}

SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Device", "version": "1.4.0", "description": "A thing on the network"},
    "servers": [{"url": "http://device.local/v1"}],
    "paths": {
        "/classify": {
            "post": {
                "operationId": "classify",
                "summary": "Label a sentence",
                "requestBody": {"content": {"application/json": {"schema": TEXT_INPUT}}},
            }
        },
        "/status": {"get": {"operationId": "status", "summary": "Current status"}},
    },
}

TOOLS = [
    {
        "name": "classify",
        "description": "Label a payload",
        "inputSchema": BYTES_INPUT,
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "reboot",
        "description": "Restart the device",
        "annotations": {"destructiveHint": True},
    },
]

SERVER_INFO = {"name": "device-mcp", "title": "Device MCP", "version": "0.3.0"}


def handler(request: httpx.Request) -> httpx.Response:
    # Only this host answers, so an address pointed anywhere else is genuinely unread.
    if request.url.host != "device.local":
        return httpx.Response(404)

    path = request.url.path
    if request.method == "GET" and path == "/openapi.json":
        return httpx.Response(200, json=SPEC)
    if request.method == "POST" and path == "/mcp":
        return _rpc(request)
    return httpx.Response(404)


def _rpc(request: httpx.Request) -> httpx.Response:
    import json

    body = json.loads(request.content or b"{}")
    result: dict[str, Any]
    if body.get("method") == "initialize":
        result = {"protocolVersion": "2025-06-18", "serverInfo": SERVER_INFO, "capabilities": {}}
    elif body.get("method") == "tools/list":
        result = {"tools": TOOLS}
    else:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601}}
        )
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": body.get("id"), "result": result},
        headers={"Mcp-Session-Id": "session-1"},
    )


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
