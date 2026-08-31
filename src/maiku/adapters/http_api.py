"""Adapt an HTTP API, with or without a spec.

Point it at an OpenAPI document and every operation becomes an affordance; point it at a
bare endpoint and you get one. The second mode matters more than it looks: most internal
APIs have no spec, and an adapter that requires one adapts nothing.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance, Unreachable
from maiku.adapters.context import CallContext
from maiku.adapters.openapi import BODY_ARGUMENT, Operation, base_url, read_spec
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import AuthRef, Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Determinism,
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
    Permissions,
    Provenance,
    RuntimeInfo,
)
from maiku.wire.events import Event, Finished
from maiku.wire.health import Health

SPEC_SUFFIXES = (".json", ".yaml", ".yml", "/openapi", "/swagger.json")


def side_effect_for(operation: Operation) -> SideEffect:
    if operation.method == "delete":
        return SideEffect.IRREVERSIBLE
    return SideEffect.READ if operation.read_only else SideEffect.EXTERNAL


def to_affordance(operation: Operation) -> Affordance:
    return Affordance(
        name=operation.name,
        summary=operation.summary,
        description=operation.description,
        kind=AffordanceKind.INVOKE,
        input_schema=operation.input_schema,
        output_schema=operation.output_schema,
        determinism=Determinism.SIDE_EFFECTING,
        latency_class=LatencyClass.SECONDS,
        idempotent=operation.idempotent,
        side_effects=side_effect_for(operation),
        tags=["http", operation.method],
    )


@register
class HTTPAdapter(Adapter):
    scheme = "http"

    def __init__(self, uri: ParticipantURI, client: Any | None = None) -> None:
        self._uri = uri
        self._url = uri.target
        self._client = client
        self._owns_client = client is None
        self._operations: dict[str, Operation] = {}
        self._info: dict[str, Any] = {}
        self._base = self._url.rstrip("/")
        self._loaded = False

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "HTTPAdapter":
        if not uri.target.startswith(("http://", "https://")):
            raise AdapterError(f"{uri.target!r} is not an http(s) URL")
        return cls(uri)

    def with_client(self, client: Any) -> "HTTPAdapter":
        adapter = HTTPAdapter(self._uri, client)
        adapter._owns_client = False
        return adapter

    @property
    def _looks_like_a_spec(self) -> bool:
        declared = self._uri.param("spec")
        if declared is not None:
            return declared.lower() not in {"0", "false", "no"}
        return self._url.endswith(SPEC_SUFFIXES)

    async def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    def _headers(self) -> dict[str, str]:
        import os

        key = os.environ.get(self._uri.param("key_env") or "", "")
        if not key:
            return {}
        header = self._uri.param("header")
        return {header: key} if header else {"Authorization": f"Bearer {key}"}

    async def _load(self) -> None:
        if self._loaded:
            return

        if not self._looks_like_a_spec:
            self._operations = {op.name: op for op in [self._bare_operation()]}
            self._loaded = True
            return

        import httpx

        client = await self._http()
        try:
            response = await client.get(self._url, headers=self._headers())
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Unreachable(f"cannot read spec at {self._url}: {exc}") from exc

        operations, self._info = read_spec(document)
        if not operations:
            raise AdapterError(f"{self._url} declares no operations")
        self._operations = {op.name: op for op in operations}
        self._base = base_url(document, self._url.rsplit("/", 1)[0])
        self._loaded = True

    def _bare_operation(self) -> Operation:
        method = (self._uri.param("method") or "get").lower()
        return Operation(
            name=self._uri.param("affordance", "call") or "call",
            method=method,
            path="",
            summary=self._uri.param("summary") or f"{method.upper()} {self._url}",
            body_is_opaque=method not in {"get", "head"},
            input_schema={
                "type": "object",
                "properties": {BODY_ARGUMENT: {"type": "object"}}
                if method not in {"get", "head"}
                else {},
            },
        )

    @property
    def _name(self) -> str:
        override = self._uri.param("name") or self._info.get("title")
        if override:
            return override.lower().replace(" ", "-")
        host = self._url.split("://", 1)[-1].split("/", 1)[0]
        return host.replace(":", "-")

    async def describe(self) -> ParticipantDescriptor:
        await self._load()
        affordances = [to_affordance(op) for op in self._operations.values()]
        return ParticipantDescriptor(
            handle=f"http/{self._name}",
            kind=Kind.SERVICE,
            display=Display(
                name=self._info.get("title") or self._name,
                description=self._info.get("description") or f"HTTP API at {self._base}",
                tags=["http", "api"],
            ),
            provenance=Provenance(
                vendor=self._name,
                version=self._info.get("version", ""),
                source_uri=self._url,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(residency=Residency.REMOTE, host=self._base, max_concurrency=8),
            affordances=affordances,
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.HTTP,
                    uri=self._base,
                    auth=AuthRef(scheme="bearer", env_var=self._uri.param("key_env"))
                    if self._uri.param("key_env")
                    else None,
                )
            ],
            io_defaults=IODefaults(
                input_modes=["application/json"], output_modes=["application/json"]
            ),
            permissions=Permissions(
                side_effects=max(
                    (a.side_effects for a in affordances),
                    key=lambda e: list(SideEffect).index(e),
                    default=SideEffect.NONE,
                ),
                egress=[self._base],
            ),
        )

    async def probe(self) -> Health:
        import httpx

        client = await self._http()
        started = time.perf_counter()
        try:
            response = await client.get(
                self._url if self._looks_like_a_spec else self._base,
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            return Health.down(f"{type(exc).__name__}: {exc}")
        if response.status_code >= 500:
            return Health.down(f"HTTP {response.status_code}")
        return Health.up((time.perf_counter() - started) * 1000)

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        await self._load()
        operation = self._operations.get(affordance)
        if operation is None:
            raise UnknownAffordance(f"{affordance!r} is not an operation on {self._name}")

        import httpx

        path = operation.path
        for name in operation.path_params:
            path = path.replace(f"{{{name}}}", str(arguments.get(name, "")))

        request: dict[str, Any] = {
            "params": {k: v for k in operation.query_params if (v := arguments.get(k)) is not None},
            "headers": {
                **self._headers(),
                **{
                    k: str(v)
                    for k in operation.header_params
                    if (v := arguments.get(k)) is not None
                },
            },
        }
        if body := _body_for(operation, arguments):
            request["json"] = body

        client = await self._http()
        try:
            response = await client.request(
                operation.method.upper(), f"{self._base}{path}", **request
            )
        except httpx.HTTPError as exc:
            raise Unreachable(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code >= 400:
            raise AdapterError(
                f"HTTP {response.status_code}: {response.text[:500]}",
                detail={"status": response.status_code},
            )

        yield Finished(result=_decode(response))

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


def _body_for(operation: Operation, arguments: dict[str, Any]) -> Any:
    if operation.body_is_opaque:
        return arguments.get(BODY_ARGUMENT)
    return {name: arguments[name] for name in operation.body_properties if name in arguments}


def _decode(response: Any) -> Any:
    if "json" in response.headers.get("content-type", ""):
        try:
            return response.json()
        except ValueError:
            pass
    return response.text
