"""The same two-protocol device, on a real socket.

The mock transport proves the readers; this proves `maiku add auto:<address>` end to end,
which is the only way to know the entry point is wired rather than merely written.
"""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.fixtures.discovery_endpoint import SERVER_INFO, SPEC, TOOLS

# Relative, so the binding points at whichever port the test happened to get.
SERVED_SPEC = {**SPEC, "servers": [{"url": "/v1"}]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/openapi.json":
            self._send(200, SERVED_SPEC)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        method = body.get("method")

        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "serverInfo": SERVER_INFO}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        else:
            self._send(200, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601}})
            return
        self._send(200, {"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    def _send(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args: object) -> None:
        return None


@contextmanager
def serving() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
