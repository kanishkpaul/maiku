"""Adapt one Philips Hue CLIP v2 light as explicit read, write and event operations."""

import asyncio
import contextlib
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance, Unreachable
from maiku.adapters.context import CallCancelled, CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor import (
    Affordance,
    AffordanceKind,
    AffordanceOperation,
    Approval,
    AuthRef,
    Binding,
    Determinism,
    Display,
    IODefaults,
    Kind,
    LatencyClass,
    ParticipantDescriptor,
    Permissions,
    Provenance,
    Residency,
    RuntimeInfo,
    SideEffect,
    Transport,
)
from maiku.wire.events import Delta, Event, Finished
from maiku.wire.health import Health
from maiku.wire.parts import DataPart

READ = "read_state"
WRITE = "write_state"
CHANGED = "state_changed"
DEFAULT_KEY_ENV = "HUE_APPLICATION_KEY"


@register
class HueAdapter(Adapter):
    """A Hue light reached through its bridge's supported local CLIP v2 API."""

    scheme = "hue"

    def __init__(self, uri: ParticipantURI, client: Any | None = None) -> None:
        self._uri = uri
        self._base = uri.target.rstrip("/")
        self._key_env = uri.param("key_env") or DEFAULT_KEY_ENV
        self._light_id = uri.param("light")
        self._client = client
        self._owns_client = client is None
        self._light: dict[str, Any] | None = None

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "HueAdapter":
        if not uri.target.startswith("https://"):
            raise AdapterError("Hue CLIP v2 requires an https:// bridge address")
        return cls(uri)

    def with_client(self, client: Any) -> "HueAdapter":
        adapter = HueAdapter(self._uri, client)
        adapter._owns_client = False
        return adapter

    async def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                verify=self._uri.flag("verify", False),
                timeout=httpx.Timeout(10.0, read=None),
            )
        return self._client

    def _headers(self, *, stream: bool = False) -> dict[str, str]:
        key = os.environ.get(self._key_env)
        if not key:
            raise AdapterError(
                f"Hue application key is missing; set environment variable {self._key_env}"
            )
        headers = {"hue-application-key": key}
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        import httpx

        client = await self._http()
        try:
            response = await client.request(
                method,
                f"{self._base}{path}",
                headers=self._headers(),
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Unreachable(f"Hue bridge request failed: {exc}") from exc
        if errors := payload.get("errors"):
            raise AdapterError("Hue bridge rejected the request", detail={"errors": errors})
        return payload

    async def _load(self) -> dict[str, Any]:
        if self._light is not None:
            return self._light

        path = "/clip/v2/resource/light"
        if self._light_id:
            path += f"/{self._light_id}"
        lights = (await self._request("GET", path)).get("data", [])
        if not lights:
            raise AdapterError("the Hue bridge returned no matching lights")
        if len(lights) > 1:
            choices = ", ".join(
                f"{light.get('id')} ({light.get('metadata', {}).get('name', 'unnamed')})"
                for light in lights
            )
            raise AdapterError(
                f"the Hue bridge has multiple lights; add ?light=<id>. Available: {choices}"
            )
        self._light = lights[0]
        self._light_id = str(self._light["id"])
        return self._light

    def _state_schema(self, light: dict[str, Any], *, writable: bool) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        if "on" in light:
            properties["on"] = {"type": "boolean"}
        if "dimming" in light:
            properties["brightness"] = {"type": "number", "minimum": 0.0, "maximum": 100.0}
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if writable:
            schema["minProperties"] = 1
        else:
            schema["required"] = list(properties)
        return schema

    async def describe(self) -> ParticipantDescriptor:
        light = await self._load()
        name = light.get("metadata", {}).get("name") or f"Hue {self._light_id}"
        slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or self._light_id
        output_schema = self._state_schema(light, writable=False)
        return ParticipantDescriptor(
            handle=f"hue/{slug}",
            kind=Kind.ROBOT,
            display=Display(
                name=name,
                description="Philips Hue light on the local bridge",
                tags=["hue", "light", "physical"],
            ),
            provenance=Provenance(
                vendor="Signify",
                source_uri=self._base,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(residency=Residency.LOCAL_SERVICE, host=self._base),
            affordances=[
                Affordance(
                    name=READ,
                    summary="Read the light state",
                    kind=AffordanceKind.PROPERTY,
                    operation=AffordanceOperation.READ,
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    output_schema=output_schema,
                    determinism=Determinism.DETERMINISTIC,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.READ,
                    scopes=["hue:read"],
                ),
                Affordance(
                    name=WRITE,
                    summary="Change the light state",
                    kind=AffordanceKind.PROPERTY,
                    operation=AffordanceOperation.WRITE,
                    input_schema=self._state_schema(light, writable=True),
                    output_schema=output_schema,
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.WRITE,
                    scopes=["hue:write"],
                ),
                Affordance(
                    name=CHANGED,
                    summary="Subscribe to changes reported by the Hue bridge",
                    kind=AffordanceKind.EVENT,
                    operation=AffordanceOperation.SUBSCRIBE,
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    output_schema={},
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.READ,
                    scopes=["hue:read"],
                ),
            ],
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.HTTP,
                    uri=f"{self._base}/clip/v2/resource/light/{self._light_id}",
                    auth=AuthRef(
                        scheme="header",
                        env_var=self._key_env,
                        header="hue-application-key",
                    ),
                )
            ],
            io_defaults=IODefaults(
                input_modes=["application/json"], output_modes=["application/json"]
            ),
            permissions=Permissions(
                scopes_required=["hue:read", "hue:write"],
                scopes_offered=["hue:read", "hue:write"],
                side_effects=SideEffect.WRITE,
                approval=Approval.ON_SCOPE,
                egress=[self._base],
            ),
        )

    async def _current_state(self) -> dict[str, Any]:
        payload = await self._request("GET", f"/clip/v2/resource/light/{self._light_id}")
        lights = payload.get("data", [])
        if not lights:
            raise AdapterError(f"Hue light {self._light_id} disappeared")
        light = lights[0]
        state: dict[str, Any] = {}
        if "on" in light:
            state["on"] = bool(light["on"]["on"])
        if "dimming" in light:
            state["brightness"] = float(light["dimming"]["brightness"])
        return state

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        raise UnknownAffordance(f"{affordance!r} is not invokable")
        yield  # pragma: no cover - keeps this an async iterator

    async def read_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != READ:
            raise UnknownAffordance(affordance)
        await self._load()
        yield Finished(result=await self._current_state())

    async def write_property(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != WRITE:
            raise UnknownAffordance(affordance)
        await self._load()
        body: dict[str, Any] = {}
        if "on" in arguments:
            body["on"] = {"on": arguments["on"]}
        if "brightness" in arguments:
            body["dimming"] = {"brightness": arguments["brightness"]}
        await self._request(
            "PUT", f"/clip/v2/resource/light/{self._light_id}", json=body
        )
        yield Finished(result=await self._current_state())

    async def subscribe(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != CHANGED:
            raise UnknownAffordance(affordance)
        await self._load()
        client = await self._http()
        try:
            async with client.stream(
                "GET",
                f"{self._base}/eventstream/clip/v2",
                headers=self._headers(stream=True),
            ) as response:
                response.raise_for_status()
                async for payload in _sse_payloads(response, ctx):
                    for update in _light_updates(payload, self._light_id or ""):
                        yield Delta(part=DataPart(data=update))
        except CallCancelled:
            raise
        except Exception as exc:
            import httpx

            if isinstance(exc, httpx.HTTPError):
                raise Unreachable(f"Hue event stream failed: {exc}") from exc
            raise

    async def probe(self) -> Health:
        started = time.perf_counter()
        try:
            await self._load()
        except Exception as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


async def _next_or_cancel(lines: Any, ctx: CallContext) -> str:
    line = asyncio.create_task(anext(lines))
    canceled = asyncio.create_task(ctx.wait_cancelled())
    try:
        done, _ = await asyncio.wait({line, canceled}, return_when=asyncio.FIRST_COMPLETED)
        if canceled in done:
            line.cancel()
            raise CallCancelled(ctx.task_id)
        canceled.cancel()
        return line.result()
    finally:
        for task in (line, canceled):
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _sse_payloads(response: Any, ctx: CallContext) -> AsyncIterator[Any]:
    lines = response.aiter_lines().__aiter__()
    data: list[str] = []
    while True:
        try:
            line = await _next_or_cancel(lines, ctx)
        except StopAsyncIteration:
            break
        if line.startswith("data:"):
            data.append(line.removeprefix("data:").lstrip())
        elif not line and data:
            try:
                yield json.loads("\n".join(data))
            except ValueError as exc:
                raise AdapterError("Hue event stream emitted invalid JSON") from exc
            data.clear()
    if data:
        yield json.loads("\n".join(data))


def _light_updates(payload: Any, light_id: str) -> list[dict[str, Any]]:
    groups = payload if isinstance(payload, list) else [payload]
    return [
        item
        for group in groups
        if isinstance(group, dict)
        for item in group.get("data", [])
        if isinstance(item, dict) and item.get("id") == light_id
    ]
