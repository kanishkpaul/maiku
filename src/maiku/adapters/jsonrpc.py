"""A minimal JSON-RPC 2.0 client over a subprocess's stdio.

Written rather than depended on: it is ~100 lines, it keeps `import maiku` free of another
package, and owning the transport is what lets the MCP adapter stay honest about framing
and lifecycle instead of inheriting someone else's assumptions.
"""

import asyncio
import json
import shlex
from typing import Any

from maiku.adapters.base import AdapterError, Unreachable


class RemoteError(AdapterError):
    code = "remote_error"

    def __init__(self, message: str, *, data: Any = None, rpc_code: int = 0) -> None:
        super().__init__(message, detail={"data": data, "code": rpc_code})
        self.rpc_code = rpc_code


class StdioClient:
    def __init__(self, command: str, cwd: str | None = None, env: dict[str, str] | None = None):
        self._command = command
        self._cwd = cwd
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0
        self._stderr: list[str] = []

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        argv = shlex.split(self._command)
        if not argv:
            raise AdapterError("empty command")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        except (OSError, ValueError) as exc:
            raise Unreachable(f"cannot start {argv[0]!r}: {exc}") from exc

        self._reader = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._drain_stderr())

    async def _read_loop(self) -> None:
        assert self._process and self._process.stdout
        try:
            while line := await self._process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue  # servers occasionally emit banner noise on stdout
                self._dispatch(message)
        finally:
            self._fail_pending(Unreachable("server closed the connection"))

    def _dispatch(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        future = self._pending.pop(message_id, None) if message_id is not None else None
        if future is None or future.done():
            return
        if error := message.get("error"):
            future.set_exception(
                RemoteError(
                    error.get("message", "remote error"),
                    data=error.get("data"),
                    rpc_code=error.get("code", 0),
                )
            )
        else:
            future.set_result(message.get("result"))

    async def _drain_stderr(self) -> None:
        assert self._process and self._process.stderr
        while line := await self._process.stderr.readline():
            self._stderr.append(line.decode(errors="replace").rstrip())
            del self._stderr[:-50]  # keep only enough to explain a failure

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _send(self, message: dict[str, Any]) -> None:
        if not self.running or self._process is None or self._process.stdin is None:
            raise Unreachable("server is not running")
        self._process.stdin.write(json.dumps(message).encode() + b"\n")
        await self._process.stdin.drain()

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0
    ) -> Any:
        self._next_id += 1
        message_id = self._next_id
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future

        await self._send(
            {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}}
        )
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            self._pending.pop(message_id, None)
            raise Unreachable(f"{method} timed out after {timeout}s") from exc

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr[-10:])

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
        self._fail_pending(Unreachable("client closed"))
        self._process = None
