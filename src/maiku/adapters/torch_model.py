"""Adapt a PyTorch module or TorchScript file.

Thin by design: the tensor wire format and the descriptor already handle arrays, so this
adapter is mostly about loading the thing, picking a device honestly, and keeping the
forward pass off the event loop.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance
from maiku.adapters.context import CallContext
from maiku.adapters.convert import to_result
from maiku.adapters.python_fn import import_target
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Determinism,
    Device,
    Kind,
    LatencyClass,
    Residency,
    SideEffect,
    Transport,
)
from maiku.descriptor.participant import (
    Display,
    IODefaults,
    ParticipantDescriptor,
    Provenance,
    Resources,
    RuntimeInfo,
)
from maiku.wire.events import Event, Finished

TENSOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "input": {
            "description": "Nested lists forming the input tensor",
            "type": "array",
        },
        "dtype": {"type": "string", "default": "float32"},
    },
    "required": ["input"],
}

TENSOR_OUTPUT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dtype": {"type": "string"},
        "shape": {"type": "array", "items": {"type": "integer"}},
        "data": {"type": "array"},
        "ref": {"type": "object"},
    },
    "required": ["dtype", "shape"],
}


def best_device(torch: Any, requested: str | None) -> tuple[str, Device]:
    """Prefer what the machine actually has, and say so in the descriptor.

    Declaring cuda on a laptop that has mps is the kind of small lie that makes a registry
    untrustworthy, so this is resolved at adapt time rather than assumed.
    """
    if requested:
        return requested, Device(requested if requested in Device.__members__.values() else "cpu")
    if torch.cuda.is_available():
        return "cuda", Device.CUDA
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", Device.MPS
    return "cpu", Device.CPU


@register
class TorchAdapter(Adapter):
    scheme = "torch"

    def __init__(self, uri: ParticipantURI) -> None:
        self._uri = uri
        self._model: Any = None
        self._torch: Any = None
        self._device = "cpu"
        self._device_enum = Device.CPU
        self._name = uri.param("name") or Path(uri.target).stem or "model"

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "TorchAdapter":
        adapter = cls(uri)
        await asyncio.to_thread(adapter._load)
        return adapter

    def _load(self) -> None:
        try:
            import torch
        except ImportError as exc:
            raise AdapterError("torch is not installed; try: pip install 'maiku[torch]'") from exc

        self._torch = torch
        self._device, self._device_enum = best_device(torch, self._uri.param("device"))

        target = self._uri.target
        if Path(target).exists():
            self._model = torch.jit.load(target, map_location=self._device)
        else:
            obj, name = import_target(target)
            self._model = obj() if isinstance(obj, type) else obj
            self._name = self._uri.param("name") or name

        if hasattr(self._model, "eval"):
            self._model.eval()
        if hasattr(self._model, "to"):
            self._model.to(self._device)

    @property
    def _parameter_bytes(self) -> int:
        if not hasattr(self._model, "parameters"):
            return 0
        return sum(p.numel() * p.element_size() for p in self._model.parameters())

    async def describe(self) -> ParticipantDescriptor:
        return ParticipantDescriptor(
            handle=f"torch/{self._name.lower()}",
            kind=Kind.MODEL,
            display=Display(
                name=self._name,
                description=f"PyTorch model on {self._device}",
                tags=["torch", "tensor", self._device],
            ),
            provenance=Provenance(
                vendor="pytorch",
                version=getattr(self._torch, "__version__", ""),
                source_uri=self._uri.raw,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(
                residency=Residency.IN_PROCESS,
                host="localhost",
                device=self._device_enum,
                resources=Resources(ram_gb=round(self._parameter_bytes / 1e9, 4) or None),
                max_concurrency=1,
            ),
            affordances=[
                Affordance(
                    name="forward",
                    summary=f"Run a forward pass through {self._name}",
                    kind=AffordanceKind.INVOKE,
                    input_schema=TENSOR_SCHEMA,
                    output_schema=TENSOR_OUTPUT,
                    determinism=Determinism.DETERMINISTIC,
                    latency_class=LatencyClass.INSTANT,
                    idempotent=True,
                    side_effects=SideEffect.NONE,
                )
            ],
            bindings=[Binding(scheme=self.scheme, transport=Transport.IN_PROCESS)],
            io_defaults=IODefaults(
                input_modes=["application/json"],
                output_modes=["application/x-maiku-tensor"],
            ),
        )

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != "forward":
            raise UnknownAffordance(f"{affordance!r} is not a torch affordance")

        torch = self._torch
        dtype = getattr(torch, arguments.get("dtype", "float32"), torch.float32)

        def run() -> Any:
            tensor = torch.tensor(arguments["input"], dtype=dtype, device=self._device)
            with torch.no_grad():
                output = self._model(tensor)
            return output.detach().to("cpu")

        try:
            output = await asyncio.to_thread(run)
        except Exception as exc:
            raise AdapterError(f"forward pass failed: {type(exc).__name__}: {exc}") from exc

        yield Finished(result=await to_result(output, ctx.artifacts))
