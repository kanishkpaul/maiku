"""A small asyncio HTTP/1.1 server for the A2A gateway.

Deliberately minimal and stdlib-only: `maiku serve a2a` should work on a bare install, and
pulling in a web framework so a local gateway can answer three routes is not a trade worth
making. It handles what the A2A surface needs - GET a card, POST JSON-RPC - and nothing else.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[str, str, bytes], Awaitable[tuple[int, Any]]]

MAX_BODY = 8 * 1024 * 1024
REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 413: "Payload Too Large"}


async def read_request(reader: asyncio.StreamReader) -> tuple[str, str, bytes] | None:
    request_line = await reader.readline()
    if not request_line:
        return None

    try:
        method, path, _ = request_line.decode("latin-1").split(" ", 2)
    except ValueError:
        return None

    length = 0
    while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
        name, _, value = line.decode("latin-1").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip() or 0)

    if length > MAX_BODY:
        raise ValueError("body too large")
    return method.upper(), path, (await reader.readexactly(length) if length else b"")


def response(status: int, payload: Any) -> bytes:
    body = json.dumps(payload, default=str).encode()
    head = (
        f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    )
    return head.encode("latin-1") + body


def serve(handler: Handler) -> Callable[..., Awaitable[None]]:
    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await read_request(reader)
            if request is None:
                return
            status, payload = await handler(*request)
        except ValueError as exc:
            status, payload = 400, {"error": str(exc)}
        except (asyncio.IncompleteReadError, ConnectionError):
            return
        except Exception as exc:
            status, payload = 400, {"error": f"{type(exc).__name__}: {exc}"}

        writer.write(response(status, payload))
        try:
            await writer.drain()
        finally:
            writer.close()

    return connected


async def run(handler: Handler, host: str = "127.0.0.1", port: int = 8080) -> None:
    server = await asyncio.start_server(serve(handler), host, port)
    async with server:
        await server.serve_forever()
