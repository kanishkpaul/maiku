"""Adapt a Hugging Face pipeline.

`hf:distilbert-base-uncased-finetuned-sst-2-english?task=sentiment-analysis` is the whole
ceremony. The task determines the affordance's shape, because a classifier, an ASR model
and an image captioner genuinely take different things - flattening them all to "text in,
text out" would be exactly the mistake this project exists to avoid.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance
from maiku.adapters.context import CallContext
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
from maiku.descriptor.hints import artifact_schema
from maiku.descriptor.participant import (
    ArtifactPolicy,
    Display,
    IODefaults,
    ParticipantDescriptor,
    Provenance,
    RuntimeInfo,
)
from maiku.wire.events import Event, Finished

TEXT_INPUT: dict[str, Any] = {
    "type": "object",
    "properties": {"inputs": {"type": "string"}},
    "required": ["inputs"],
}

FILE_TASKS = {
    "automatic-speech-recognition": ("audio/*", ["audio"]),
    "image-classification": ("image/*", ["vision"]),
    "image-to-text": ("image/*", ["vision"]),
    "object-detection": ("image/*", ["vision"]),
}

DEFAULT_TASK = "text-generation"


def input_for(task: str) -> tuple[dict[str, Any], list[str]]:
    media_type, tags = FILE_TASKS.get(task, ("", []))
    if not media_type:
        return dict(TEXT_INPUT), ["text"]
    return {
        "type": "object",
        "properties": {"inputs": artifact_schema(media_type)},
        "required": ["inputs"],
    }, tags


@register
class HuggingFaceAdapter(Adapter):
    scheme = "hf"

    def __init__(self, uri: ParticipantURI) -> None:
        self._uri = uri
        self._model_id = uri.target
        self._task = uri.param("task") or DEFAULT_TASK
        self._pipeline: Any = None
        self._device = Device.CPU

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "HuggingFaceAdapter":
        adapter = cls(uri)
        await asyncio.to_thread(adapter._load)
        return adapter

    def _load(self) -> None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise AdapterError(
                "transformers is not installed; try: pip install 'maiku[hf]'"
            ) from exc

        requested = self._uri.param("device")
        self._device = Device(requested) if requested else _detect_device()
        self._pipeline = pipeline(
            task=self._task,
            model=self._model_id,
            device=None if self._device is Device.CPU else self._device.value,
        )

    @property
    def _affordance_name(self) -> str:
        return self._task.replace("-", "_")

    async def describe(self) -> ParticipantDescriptor:
        schema, tags = input_for(self._task)
        media_type = FILE_TASKS.get(self._task, ("", []))[0]

        return ParticipantDescriptor(
            handle=f"hf/{self._model_id.lower().replace('/', '--')}",
            kind=Kind.MODEL,
            display=Display(
                name=self._model_id,
                description=f"Hugging Face {self._task} pipeline",
                tags=["huggingface", self._task, *tags],
            ),
            provenance=Provenance(
                vendor="huggingface",
                version=self._model_id,
                source_uri=f"https://huggingface.co/{self._model_id}",
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(
                residency=Residency.IN_PROCESS,
                host="localhost",
                device=self._device,
                max_concurrency=1,
            ),
            affordances=[
                Affordance(
                    name=self._affordance_name,
                    summary=f"Run {self._task} with {self._model_id}",
                    kind=AffordanceKind.INVOKE,
                    input_schema=schema,
                    determinism=Determinism.DETERMINISTIC
                    if self._task not in {"text-generation"}
                    else Determinism.STOCHASTIC,
                    latency_class=LatencyClass.SECONDS,
                    idempotent=self._task != "text-generation",
                    side_effects=SideEffect.NONE,
                    tags=tags,
                )
            ],
            bindings=[Binding(scheme=self.scheme, transport=Transport.IN_PROCESS)],
            io_defaults=IODefaults(
                input_modes=[media_type or "text/plain"], output_modes=["application/json"]
            ),
            artifacts=ArtifactPolicy(can_read=[media_type] if media_type else []),
        )

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance != self._affordance_name:
            raise UnknownAffordance(f"{affordance!r} is not {self._task}")

        inputs = arguments["inputs"]
        if self._task in FILE_TASKS:
            if ctx.artifacts is None:
                raise AdapterError(f"{self._task} needs an artifact store")
            inputs = str(await ctx.artifacts.path(inputs))

        extra = {k: v for k, v in arguments.items() if k != "inputs"}
        try:
            output = await asyncio.to_thread(lambda: self._pipeline(inputs, **extra))
        except Exception as exc:
            raise AdapterError(f"{self._task} failed: {type(exc).__name__}: {exc}") from exc

        yield Finished(result=output)


def _detect_device() -> Device:
    try:
        import torch
    except ImportError:
        return Device.CPU
    if torch.cuda.is_available():
        return Device.CUDA
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return Device.MPS
    return Device.CPU
