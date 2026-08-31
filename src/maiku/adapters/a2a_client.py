"""Ingest a remote A2A agent.

Closes the loop on the projections: a participant adapted from anywhere can be served out
as an A2A agent, and an A2A agent can be adapted back in. Nothing in the runtime knows
which side of that a given participant came from.

Skills carry no schemas in A2A, so an ingested agent gets the message-shaped input rather
than a fabricated one - the same honesty the projection module applies in reverse.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance, Unreachable
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.projections.a2a import from_agent_card
from maiku.wire.events import ArtifactWritten, Delta, Event, Finished, Progress
from maiku.wire.health import Health
from maiku.wire.parts import TextPart
from maiku.wire.task import TaskState

WELL_KNOWN = "/.well-known/agent-card.json"
TERMINAL = {"completed", "failed", "canceled", "rejected"}
FAILED = {"failed", "rejected"}


def card_url(target: str) -> str:
    return target if target.endswith(".json") else target.rstrip("/") + WELL_KNOWN


def text_of(parts: list[dict[str, Any]]) -> str:
    return "".join(p.get("text", "") for p in parts if p.get("kind", "text") == "text")


@register
class A2AAdapter(Adapter):
    scheme = "a2a"

    def __init__(self, uri: ParticipantURI, client: Any | None = None) -> None:
        self._uri = uri
        self._card_url = card_url(uri.target)
        self._card: dict[str, Any] = {}
        self._client = client
        self._owns_client = client is None
        self._poll_interval = float(uri.param("poll", "0.5") or 0.5)
        self._deadline = float(uri.param("timeout", "120") or 120)

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "A2AAdapter":
        if not uri.target.startswith(("http://", "https://")):
            raise AdapterError(f"{uri.target!r} is not an http(s) agent URL")
        return cls(uri)

    def with_client(self, client: Any) -> "A2AAdapter":
        adapter = A2AAdapter(self._uri, client)
        adapter._owns_client = False
        return adapter

    async def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        return self._client

    async def _load_card(self) -> dict[str, Any]:
        if self._card:
            return self._card
        import httpx

        client = await self._http()
        try:
            response = await client.get(self._card_url)
            response.raise_for_status()
            self._card = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Unreachable(f"cannot read agent card at {self._card_url}: {exc}") from exc
        return self._card

    @property
    def _endpoint(self) -> str:
        return self._card.get("url") or self._uri.target

    async def describe(self) -> ParticipantDescriptor:
        card = await self._load_card()
        return from_agent_card(card, handle=self._uri.param("handle"))

    async def probe(self) -> Health:
        import httpx

        started = time.perf_counter()
        try:
            client = await self._http()
            response = await client.get(self._card_url, timeout=5.0)
        except httpx.HTTPError as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        if response.status_code >= 400:
            return Health.down(f"HTTP {response.status_code}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        client = await self._http()
        try:
            response = await client.post(
                self._endpoint,
                json={
                    "jsonrpc": "2.0",
                    "id": uuid.uuid4().hex,
                    "method": method,
                    "params": params,
                },
            )
        except httpx.HTTPError as exc:
            raise Unreachable(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code >= 400:
            raise Unreachable(f"HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        if error := payload.get("error"):
            raise AdapterError(error.get("message", "agent returned an error"), detail=error)
        return payload.get("result") or {}

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        descriptor = await self.descriptor()
        try:
            descriptor.affordance(affordance)
        except KeyError as exc:
            raise UnknownAffordance(str(exc)) from exc

        result = await self._rpc(
            "message/send",
            {
                "message": {
                    "role": "user",
                    "messageId": uuid.uuid4().hex,
                    "parts": [{"kind": "text", "text": arguments["message"]}],
                    "metadata": {"maiku/skill": affordance},
                },
                **({"parts": arguments["parts"]} if arguments.get("parts") else {}),
            },
        )

        # A2A may answer with a finished Message or with a Task that has to be followed.
        if result.get("kind") == "message" or "status" not in result:
            yield Finished(result=text_of(result.get("parts") or []))
            return

        async for event in self._follow(result, ctx):
            yield event

    async def _follow(self, task: dict[str, Any], ctx: CallContext) -> AsyncIterator[Event]:
        expires = time.time() + self._deadline
        state = (task.get("status") or {}).get("state", "submitted")
        seen_artifacts: set[str] = set()
        index = 0

        while True:
            for artifact in task.get("artifacts") or []:
                if (key := artifact.get("artifactId") or json.dumps(artifact)) in seen_artifacts:
                    continue
                seen_artifacts.add(key)
                if event := await self._store(artifact, ctx):
                    yield event

            if state in TERMINAL:
                break
            if time.time() > expires:
                raise Unreachable(f"agent task stalled in {state!r}")

            ctx.raise_if_cancelled()
            yield Progress(message=f"remote task is {state}")
            index += 1

            import asyncio

            await asyncio.sleep(self._poll_interval)
            task = await self._rpc("tasks/get", {"id": task["id"]})
            state = (task.get("status") or {}).get("state", state)

        text = "".join(text_of(entry.get("parts") or []) for entry in (task.get("artifacts") or []))
        if not text:
            text = text_of(((task.get("status") or {}).get("message") or {}).get("parts") or [])

        if state in FAILED:
            raise AdapterError(text or f"remote task {state}")
        if text:
            yield Delta(part=TextPart(text=text), index=index)
        yield Finished(
            state=TaskState.CANCELED if state == "canceled" else TaskState.COMPLETED,
            result=text,
        )

    async def _store(self, artifact: dict[str, Any], ctx: CallContext) -> Event | None:
        if ctx.artifacts is None:
            return None
        for part in artifact.get("parts") or []:
            file = part.get("file") or {}
            if payload := file.get("bytes"):
                import base64

                ref = await ctx.artifacts.write(
                    base64.b64decode(payload),
                    media_type=file.get("mimeType", "application/octet-stream"),
                    name=file.get("name") or artifact.get("name"),
                )
                return ArtifactWritten(ref=ref)
        return None

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
