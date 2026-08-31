"""A real MCP server over stdio, small enough to read and honest about the protocol.

Testing the adapter against a genuine JSON-RPC handshake rather than a mock is the only way
to know the framing, initialize sequence and content-block handling are right.
"""

import base64
import json
import sys

PIXEL = base64.b64encode(b"\x89PNG\r\n\x1a\n-not-really-a-png").decode()

TOOLS = [
    {
        "name": "read_file",
        "title": "Read a file",
        "description": "Return the contents of a path",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
    {
        "name": "delete-everything",
        "description": "Exactly what it says",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "render_chart",
        "description": "Produce an image",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "unwritten",
        "description": "A tool with no annotations at all",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call(name, arguments):
    if name == "read_file":
        if arguments["path"] == "camera-notes.md":
            return {"content": [{"type": "text", "text": "camera 3 faces the loading bay"}]}
        return {"content": [{"type": "text", "text": f"contents of {arguments['path']}"}]}
    if name == "render_chart":
        return {
            "content": [
                {"type": "text", "text": f"chart: {arguments['title']}"},
                {"type": "image", "data": PIXEL, "mimeType": "image/png"},
            ]
        }
    if name == "delete-everything":
        return {"content": [{"type": "text", "text": "refused"}], "isError": True}
    return {"content": [{"type": "text", "text": "ok"}]}


def handle(message):
    method = message.get("method")
    if method == "initialize":
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fixture", "title": "Fixture Server", "version": "9.9.9"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = message.get("params") or {}
        return call(params["name"], params.get("arguments") or {})
    raise LookupError(method)


def main():
    print("fixture server starting", file=sys.stderr, flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if "id" not in message:
            continue

        try:
            response = {"jsonrpc": "2.0", "id": message["id"], "result": handle(message)}
        except LookupError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": f"no such method: {exc}"},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
