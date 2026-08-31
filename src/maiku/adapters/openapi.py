"""Reading an OpenAPI document into affordances.

Kept separate from the adapter that calls the API, because turning a spec into a plan is
where all the fiddliness lives and it is worth being able to test it without a socket.
"""

from dataclasses import dataclass, field
from typing import Any

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
READ_METHODS = frozenset({"get", "head", "options"})
IDEMPOTENT_METHODS = frozenset({"get", "head", "options", "put", "delete"})
BODY_ARGUMENT = "body"
MAX_REF_DEPTH = 20


def resolve_refs(node: Any, document: dict[str, Any], depth: int = 0) -> Any:
    """Inline local $refs so downstream code only ever sees plain JSON Schema.

    Depth-limited rather than cycle-tracked: a recursive schema should degrade to an
    untyped object, not hang the adapter that read it.
    """
    if depth > MAX_REF_DEPTH:
        return {}
    if isinstance(node, list):
        return [resolve_refs(item, document, depth + 1) for item in node]
    if not isinstance(node, dict):
        return node

    if isinstance(ref := node.get("$ref"), str) and ref.startswith("#/"):
        target: Any = document
        for step in ref[2:].split("/"):
            if not isinstance(target, dict) or step not in target:
                return {}
            target = target[step]
        return resolve_refs(target, document, depth + 1)

    return {key: resolve_refs(value, document, depth + 1) for key, value in node.items()}


@dataclass(slots=True)
class Operation:
    name: str
    method: str
    path: str
    summary: str = ""
    description: str = ""
    path_params: list[str] = field(default_factory=list)
    query_params: list[str] = field(default_factory=list)
    header_params: list[str] = field(default_factory=list)
    body_properties: list[str] = field(default_factory=list)
    body_is_opaque: bool = False
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def read_only(self) -> bool:
        return self.method in READ_METHODS

    @property
    def idempotent(self) -> bool:
        return self.method in IDEMPOTENT_METHODS


def _slug(value: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in value.lower())
    return "_".join(part for part in cleaned.split("_") if part) or "call"


def _json_body(operation: dict[str, Any]) -> dict[str, Any]:
    content = (operation.get("requestBody") or {}).get("content") or {}
    for media_type, entry in content.items():
        if "json" in media_type:
            return entry.get("schema") or {}
    return {}


def _success_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") or {}
    for status in ("200", "201", "2XX", "default"):
        content = (responses.get(status) or {}).get("content") or {}
        for media_type, entry in content.items():
            if "json" in media_type:
                return entry.get("schema") or {}
    return {}


def build_operation(
    path: str, method: str, spec: dict[str, Any], shared: list[dict[str, Any]]
) -> Operation:
    operation = Operation(
        name=_slug(spec.get("operationId") or f"{method}_{path}"),
        method=method,
        path=path,
        summary=(spec.get("summary") or f"{method.upper()} {path}")[:200],
        description=spec.get("description") or "",
    )

    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in [*shared, *(spec.get("parameters") or [])]:
        name, location = parameter.get("name"), parameter.get("in")
        if not name or location not in {"path", "query", "header"}:
            continue
        properties[name] = parameter.get("schema") or {"type": "string"}
        if description := parameter.get("description"):
            properties[name] = {**properties[name], "description": description}
        if parameter.get("required") or location == "path":
            required.append(name)
        getattr(operation, f"{location}_params").append(name)

    body = _json_body(spec)
    if body.get("type") == "object" and body.get("properties"):
        # Flatten the body into the argument list: callers think in fields, not envelopes.
        operation.body_properties = list(body["properties"])
        properties.update(body["properties"])
        required.extend(body.get("required") or [])
    elif body:
        operation.body_is_opaque = True
        properties[BODY_ARGUMENT] = body
        required.append(BODY_ARGUMENT)

    operation.input_schema = {
        "type": "object",
        "properties": properties,
        "required": sorted(set(required)),
    }
    operation.output_schema = _success_schema(spec)
    return operation


def read_spec(document: dict[str, Any]) -> tuple[list[Operation], dict[str, Any]]:
    resolved = resolve_refs(document, document)
    operations: list[Operation] = []

    for path, entry in (resolved.get("paths") or {}).items():
        if not isinstance(entry, dict):
            continue
        shared = entry.get("parameters") or []
        for method in METHODS:
            if isinstance(spec := entry.get(method), dict):
                operations.append(build_operation(path, method, spec, shared))

    seen: dict[str, int] = {}
    for operation in operations:
        seen[operation.name] = seen.get(operation.name, 0) + 1
        if seen[operation.name] > 1:
            operation.name = f"{operation.name}_{seen[operation.name]}"

    return operations, resolved.get("info") or {}


def base_url(document: dict[str, Any], fallback: str) -> str:
    servers = document.get("servers") or []
    url = servers[0].get("url") if servers and isinstance(servers[0], dict) else None
    if not url or url.startswith("/"):
        return fallback.rstrip("/") + (url or "").rstrip("/")
    return url.rstrip("/")
