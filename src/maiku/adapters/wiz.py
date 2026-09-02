"""Adapt one WiZ Connected light through its local UDP control API."""

import asyncio
import contextlib
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
DEFAULT_PORT = 38899


@register
class WizAdapter(Adapter):
    """A WiZ light reached directly on the LAN, without a cloud credential or bridge."""

    scheme = "wiz"

    def __init__(self, uri: ParticipantURI, bulb: Any) -> None:
        self._uri = uri
        self._bulb = bulb
        self._bulb_type: Any | None = None
        self._state: Any | None = None

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "WizAdapter":
        try:
            from pywizlight import discovery, wizlight
        except ImportError as exc:  # pragma: no cover - exercised without the optional extra
            raise AdapterError("WiZ support requires: uv sync --extra wiz") from exc

        port = int(uri.param("port", str(DEFAULT_PORT)) or DEFAULT_PORT)
        target = uri.target.strip()
        if target not in {"auto", "discover"}:
            if not target:
                raise AdapterError("use wiz:discover or wiz:<bulb-ip>")
            return cls(uri, wizlight(target, port=port, mac=uri.param("mac")))

        bulbs = await discovery.discover_lights(
            broadcast_space=uri.param("broadcast", "255.255.255.255") or "255.255.255.255",
            wait_time=float(uri.param("wait", "5") or 5),
        )
        wanted_mac = (uri.param("mac") or "").replace(":", "").lower()
        if wanted_mac:
            bulbs = [
                bulb
                for bulb in bulbs
                if (bulb.mac or "").replace(":", "").lower() == wanted_mac
            ]
        if not bulbs:
            raise Unreachable(
                "no WiZ light answered local discovery; check that this machine and the light "
                "share a LAN and that local communication is enabled in the WiZ app"
            )
        if len(bulbs) > 1:
            choices = ", ".join(f"{bulb.ip} ({bulb.mac or 'unknown mac'})" for bulb in bulbs)
            for bulb in bulbs:
                await bulb.async_close()
            raise AdapterError(
                "multiple WiZ lights answered; use wiz:<ip> or "
                f"wiz:discover?mac=<mac>. Available: {choices}"
            )
        return cls(uri, bulbs[0])

    def with_bulb(self, bulb: Any) -> "WizAdapter":
        """Return an equivalent adapter backed by a conformance-test bulb."""
        return WizAdapter(self._uri, bulb)

    async def _load(self) -> tuple[Any, Any]:
        if self._bulb_type is not None and self._state is not None:
            return self._bulb_type, self._state
        try:
            self._bulb_type = await self._bulb.get_bulbtype()
            states = await self._bulb.updateState()
        except Exception as exc:
            raise Unreachable(f"WiZ light at {self._bulb.ip} did not answer: {exc}") from exc
        if not states or states[0] is None:
            raise Unreachable(f"WiZ light at {self._bulb.ip} returned no state")
        self._state = states[0]
        return self._bulb_type, self._state

    def _state_schema(self, *, writable: bool) -> dict[str, Any]:
        features = self._bulb_type.features
        properties: dict[str, Any] = {"on": {"type": "boolean"}}
        if features.brightness:
            properties["brightness"] = {"type": "integer", "minimum": 0, "maximum": 255}
        if features.color_tmp and self._bulb_type.kelvin_range:
            properties["color_temperature"] = {
                "type": "integer",
                "minimum": self._bulb_type.kelvin_range.min,
                "maximum": self._bulb_type.kelvin_range.max,
            }
        if features.color:
            properties["rgb"] = {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 255},
                "minItems": 3,
                "maxItems": 3,
            }
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if writable:
            schema["minProperties"] = 1
        else:
            schema["required"] = ["on"]
        return schema

    async def describe(self) -> ParticipantDescriptor:
        bulb_type, state = await self._load()
        mac = state.get_mac() or await self._bulb.getMac()
        identity = (mac or self._bulb.ip).replace(":", "").lower()
        slug = re.sub(r"[^a-z0-9._-]+", "-", identity).strip("-")
        name = bulb_type.name or f"WiZ light {identity[-6:]}"
        output_schema = self._state_schema(writable=False)
        endpoint = f"udp://{self._bulb.ip}:{self._bulb.port}"
        return ParticipantDescriptor(
            handle=f"wiz/{slug}",
            kind=Kind.ROBOT,
            display=Display(
                name=name,
                description="WiZ Connected light on the local network",
                tags=["wiz", "light", "physical", "local"],
            ),
            provenance=Provenance(
                vendor="Signify",
                version=bulb_type.fw_version or "",
                source_uri=endpoint,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(residency=Residency.LOCAL_SERVICE, host=self._bulb.ip),
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
                    scopes=["wiz:read"],
                ),
                Affordance(
                    name=WRITE,
                    summary="Change the light state",
                    kind=AffordanceKind.PROPERTY,
                    operation=AffordanceOperation.WRITE,
                    input_schema=self._state_schema(writable=True),
                    output_schema=output_schema,
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.WRITE,
                    scopes=["wiz:write"],
                ),
                Affordance(
                    name=CHANGED,
                    summary="Subscribe to state changes pushed by the light",
                    kind=AffordanceKind.EVENT,
                    operation=AffordanceOperation.SUBSCRIBE,
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    output_schema=output_schema,
                    determinism=Determinism.SIDE_EFFECTING,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.READ,
                    scopes=["wiz:read"],
                ),
            ],
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.UDP,
                    uri=endpoint,
                    auth=AuthRef(scheme="none", note="WiZ local control uses no cloud credential"),
                )
            ],
            io_defaults=IODefaults(
                input_modes=["application/json"], output_modes=["application/json"]
            ),
            permissions=Permissions(
                scopes_required=["wiz:read", "wiz:write"],
                scopes_offered=["wiz:read", "wiz:write"],
                side_effects=SideEffect.WRITE,
                approval=Approval.ON_SCOPE,
                egress=[self._bulb.ip],
            ),
        )

    def _normalized(self, state: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"on": bool(state.get_state())}
        features = self._bulb_type.features
        if features.brightness and (brightness := state.get_brightness()) is not None:
            result["brightness"] = brightness
        if features.color_tmp and (temperature := state.get_colortemp()) is not None:
            result["color_temperature"] = temperature
        if features.color:
            rgb = state.get_rgb()
            if all(channel is not None for channel in rgb):
                result["rgb"] = list(rgb)
        return result

    async def _current_state(self) -> dict[str, Any]:
        try:
            states = await self._bulb.updateState()
        except Exception as exc:
            raise Unreachable(f"WiZ light at {self._bulb.ip} did not answer: {exc}") from exc
        if not states or states[0] is None:
            raise Unreachable(f"WiZ light at {self._bulb.ip} returned no state")
        self._state = states[0]
        return self._normalized(self._state)

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        raise UnknownAffordance(f"{affordance!r} is not invokable")
        yield  # pragma: no cover

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
        from pywizlight import PilotBuilder

        builder = PilotBuilder(
            state=arguments.get("on"),
            brightness=arguments.get("brightness"),
            colortemp=arguments.get("color_temperature"),
            rgb=tuple(arguments["rgb"]) if "rgb" in arguments else None,
        )
        try:
            await self._bulb.send(builder.set_pilot_message())
        except Exception as exc:
            raise Unreachable(f"WiZ light at {self._bulb.ip} rejected the write: {exc}") from exc
        yield Finished(result=await self._current_state())

    async def subscribe(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != CHANGED:
            raise UnknownAffordance(affordance)
        await self._load()
        queue: asyncio.Queue[Any] = asyncio.Queue()

        def changed(states: list[Any | None]) -> None:
            if states and states[0] is not None:
                queue.put_nowait(states[0])

        try:
            if not await self._bulb.start_push(changed):
                raise Unreachable("the WiZ light could not start local push updates")
            while True:
                next_state = asyncio.create_task(queue.get())
                cancelled = asyncio.create_task(ctx.wait_cancelled())
                done, _ = await asyncio.wait(
                    {next_state, cancelled}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancelled in done:
                    next_state.cancel()
                    raise CallCancelled(ctx.task_id)
                cancelled.cancel()
                state = next_state.result()
                self._state = state
                yield Delta(part=DataPart(data=self._normalized(state)))
        finally:
            for task in (locals().get("next_state"), locals().get("cancelled")):
                if task is not None and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            if getattr(self._bulb, "push_cancel", None):
                self._bulb.push_cancel()
                self._bulb.push_cancel = None
            if hasattr(self._bulb, "push_running"):
                self._bulb.push_running = False

    async def probe(self) -> Health:
        started = time.perf_counter()
        try:
            await self._load()
        except Exception as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def close(self) -> None:
        await self._bulb.async_close()
