"""Read an address that publishes an OpenAPI document.

All the derivation already exists: `adapters.openapi.read_spec` turns a document into
operations and `adapters.http_api.to_affordance` turns an operation into an affordance.
This module only finds the document and says what it tried when it cannot.
"""

from typing import Any

from maiku.adapters.http_api import to_affordance
from maiku.adapters.openapi import base_url, read_spec
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import Kind, Transport
from maiku.descriptor.participant import Display, Provenance
from maiku.discovery.base import Address, Attempt, NotReadable, Reading

# Where specs are published in practice, most conventional first.
SPEC_PATHS = ("/openapi.json", "/swagger.json", "/v3/api-docs", "/.well-known/openapi.json")
SPEC_SUFFIXES = (".json", ".yaml", ".yml", "/openapi", "/swagger.json")


def is_openapi(document: Any) -> bool:
    """A declared OpenAPI document, not something that merely looks API-shaped.

    Rule 3: capability is read from what a thing publishes about itself. A JSON body with
    no `openapi` or `swagger` key has published nothing, and inferring one would be a
    guess.
    """
    return (
        isinstance(document, dict)
        and bool(document.get("openapi") or document.get("swagger"))
        and isinstance(document.get("paths"), dict)
    )


class OpenAPIDiscoverer:
    name = "openapi"
    precedence = 30

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        # `applies` and `read` share one lookup so the whole discovery costs one pass over
        # the candidate paths rather than two.
        self._found: dict[str, tuple[str, dict[str, Any]]] = {}
        self._missed: dict[str, list[Attempt]] = {}

    async def applies(self, address: Address) -> bool:
        return await self._locate(address) is not None

    async def read(self, address: Address) -> Reading:
        located = await self._locate(address)
        if located is None:
            raise NotReadable(self.name, self._missed.get(address.url, []))

        spec_url, document = located
        operations, info = read_spec(document)
        if not operations:
            raise NotReadable(self.name, [Attempt(spec_url, "declares no operations")])

        base = base_url(document, spec_url.rsplit("/", 1)[0])
        return Reading(
            source=self.name,
            affordances=[to_affordance(op) for op in operations],
            binding=Binding(scheme="http", transport=Transport.HTTP, uri=base),
            kind=Kind.SERVICE,
            display=Display(
                name=info.get("title") or address.slug,
                description=info.get("description") or "",
                tags=["http", "api"],
            ),
            provenance=Provenance(
                vendor=info.get("title", ""),
                version=info.get("version", ""),
                license=((info.get("license") or {}).get("name") or ""),
            ),
            attempts=(Attempt(spec_url, "read"),),
        )

    def candidates(self, address: Address) -> list[str]:
        if address.url.endswith(SPEC_SUFFIXES):
            return [address.url]
        return [address.join(path) for path in SPEC_PATHS]

    async def _locate(self, address: Address) -> tuple[str, dict[str, Any]] | None:
        if (cached := self._found.get(address.url)) is not None:
            return cached

        attempts: list[Attempt] = []
        for candidate in self.candidates(address):
            document, outcome = await self._fetch(candidate)
            attempts.append(Attempt(candidate, outcome))
            if document is not None:
                self._found[address.url] = (candidate, document)
                return self._found[address.url]

        self._missed[address.url] = attempts
        return None

    async def _fetch(self, url: str) -> tuple[dict[str, Any] | None, str]:
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            return None, f"{type(exc).__name__}: {exc}"

        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}"
        try:
            document = response.json()
        except ValueError:
            return None, "response is not JSON"
        if not is_openapi(document):
            return None, "JSON, but declares no openapi or swagger version"
        return document, "read"

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
