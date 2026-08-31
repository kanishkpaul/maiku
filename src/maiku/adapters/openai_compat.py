"""Anything that speaks the OpenAI chat wire format.

One adapter covers frontier APIs, Ollama, LM Studio, llama.cpp's server, vLLM and
OpenRouter, because they all converged on the same endpoint shape. The scheme table below
is just defaults - the protocol work is written once.

Talking the wire format directly rather than depending on a gateway library keeps the
dependency to httpx and keeps `import maiku` free of it.
"""

import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance, Unreachable
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import AuthRef, Binding
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
    RuntimeInfo,
)
from maiku.wire.events import Delta, Event, Finished, Usage
from maiku.wire.health import Health
from maiku.wire.parts import TextPart

DONE = "[DONE]"
SSE_PREFIX = "data: "


@dataclass(frozen=True, slots=True)
class Flavour:
    scheme: str
    base_url: str
    key_env: str | None
    vendor: str
    residency: Residency
    device: Device = Device.NONE


FLAVOURS: tuple[Flavour, ...] = (
    Flavour("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "openai", Residency.REMOTE),
    Flavour(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "openrouter",
        Residency.REMOTE,
    ),
    Flavour(
        "ollama",
        "http://localhost:11434/v1",
        None,
        "ollama",
        Residency.LOCAL_SERVICE,
        Device.MPS,
    ),
    Flavour(
        "lmstudio",
        "http://localhost:1234/v1",
        None,
        "lmstudio",
        Residency.LOCAL_SERVICE,
        Device.MPS,
    ),
    Flavour("vllm", "http://localhost:8000/v1", None, "vllm", Residency.LOCAL_SERVICE),
)

BY_SCHEME = {f.scheme: f for f in FLAVOURS}

MESSAGES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "role": {"enum": ["system", "user", "assistant"]},
                    "content": {"type": "string"},
                },
                "required": ["role", "content"],
            },
        },
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1},
        "stop": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["messages"],
}

PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "system": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1},
    },
    "required": ["prompt"],
}


def _affordances() -> list[Affordance]:
    shared = {
        "output_schema": {"type": "string"},
        "kind": AffordanceKind.STREAM,
        "determinism": Determinism.STOCHASTIC,
        "latency_class": LatencyClass.SECONDS,
        "side_effects": SideEffect.NONE,
        "idempotent": False,
    }
    return [
        Affordance(
            name="chat",
            summary="Continue a conversation",
            description="Full message list in, generated assistant turn out.",
            input_schema=MESSAGES_SCHEMA,
            **shared,
        ),
        Affordance(
            name="complete",
            summary="Answer a single prompt",
            description="Convenience over chat for callers that have no conversation.",
            input_schema=PROMPT_SCHEMA,
            **shared,
        ),
    ]


class OpenAICompatible(Adapter):
    scheme = "openai"

    def __init__(self, uri: ParticipantURI, flavour: Flavour, client: Any | None = None) -> None:
        self._uri = uri
        self._flavour = flavour
        self._model = uri.target
        self._base = (uri.param("base") or flavour.base_url).rstrip("/")
        self._key_env = uri.param("key_env") or flavour.key_env
        self._client = client
        self._owns_client = client is None

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "OpenAICompatible":
        flavour = BY_SCHEME.get(uri.scheme)
        if flavour is None:
            raise AdapterError(f"{uri.scheme!r} is not an OpenAI-compatible flavour")
        if not uri.target:
            raise AdapterError(f"{uri.raw!r} names no model")
        return cls(uri, flavour)

    def with_client(self, client: Any) -> "OpenAICompatible":
        adapter = OpenAICompatible(self._uri, self._flavour, client)
        adapter._owns_client = False
        return adapter

    @property
    def handle(self) -> str:
        return f"{self._flavour.scheme}/{self._model.lower()}"

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self._key_env or "", "")
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        return self._client

    async def describe(self) -> ParticipantDescriptor:
        flavour = self._flavour
        return ParticipantDescriptor(
            handle=self.handle,
            kind=Kind.MODEL,
            display=Display(
                name=self._model,
                description=f"{flavour.vendor} chat model served at {self._base}",
                tags=["llm", "chat", flavour.vendor],
            ),
            provenance=Provenance(
                vendor=flavour.vendor,
                version=self._model,
                source_uri=self._base,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(
                residency=flavour.residency,
                host=self._base,
                device=flavour.device,
                max_concurrency=int(self._uri.param("concurrency", "4") or 4),
            ),
            affordances=_affordances(),
            bindings=[
                Binding(
                    scheme=flavour.scheme,
                    transport=Transport.HTTP,
                    uri=f"{self._base}/chat/completions",
                    auth=AuthRef(scheme="bearer", env_var=self._key_env) if self._key_env else None,
                    config={"model": self._model},
                )
            ],
            io_defaults=IODefaults(
                input_modes=["text/plain", "application/json"],
                output_modes=["text/plain"],
            ),
        )

    async def probe(self) -> Health:
        import httpx

        client = await self._http()
        started = time.perf_counter()
        try:
            response = await client.get(
                f"{self._base}/models", headers=self._headers(), timeout=5.0
            )
        except httpx.HTTPError as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")

        if response.status_code >= 400:
            return Health.down(f"HTTP {response.status_code}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        if affordance == "complete":
            payload = _from_prompt(arguments)
        elif affordance == "chat":
            payload = dict(arguments)
        else:
            raise UnknownAffordance(f"{affordance!r} is not a chat affordance")

        body = {
            "model": self._model,
            "stream": True,
            "stream_options": {"include_usage": True},
            **{k: v for k, v in payload.items() if v is not None},
        }

        text: list[str] = []
        usage: dict[str, Any] | None = None
        index = 0

        async for chunk in self._stream(body):
            ctx.raise_if_cancelled()
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or ():
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    text.append(piece)
                    yield Delta(part=TextPart(text=piece), index=index)
                    index += 1

        if usage:
            yield Usage(
                unit="token",
                amount=float(usage.get("total_tokens") or 0),
                tokens_in=usage.get("prompt_tokens"),
                tokens_out=usage.get("completion_tokens"),
            )
        yield Finished(result="".join(text))

    async def _stream(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        client = await self._http()
        try:
            async with client.stream(
                "POST",
                f"{self._base}/chat/completions",
                json=body,
                headers={**self._headers(), "Accept": "text/event-stream"},
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(errors="replace")[:500]
                    raise Unreachable(f"HTTP {response.status_code}: {detail}")
                async for line in response.aiter_lines():
                    if not line.startswith(SSE_PREFIX):
                        continue
                    payload = line[len(SSE_PREFIX) :].strip()
                    if payload == DONE:
                        return
                    try:
                        yield json.loads(payload)
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPError as exc:
            raise Unreachable(f"{type(exc).__name__}: {exc}") from exc

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


def _from_prompt(arguments: dict[str, Any]) -> dict[str, Any]:
    messages = []
    if system := arguments.get("system"):
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": arguments["prompt"]})
    return {
        "messages": messages,
        "temperature": arguments.get("temperature"),
        "max_tokens": arguments.get("max_tokens"),
    }


# One implementation, several front doors: the flavours differ only in defaults.
for _flavour in FLAVOURS:
    register(
        type(
            f"{_flavour.scheme.title()}Adapter",
            (OpenAICompatible,),
            {"scheme": _flavour.scheme},
        )
    )
