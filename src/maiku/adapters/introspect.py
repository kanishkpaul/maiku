"""Deriving affordances from Python objects.

Every adapter that fronts real Python code (plain functions, HF pipelines, torch modules)
reuses this. Inference is not a convenience here — a descriptor a human has to write by
hand is a descriptor that never gets written.
"""

import inspect
import textwrap
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, get_type_hints

from pydantic import TypeAdapter, create_model

from maiku.descriptor.affordance import EMPTY_OBJECT_SCHEMA, Affordance
from maiku.descriptor.enums import AffordanceKind, Determinism, LatencyClass

SKIP_PARAMS = frozenset({"self", "cls"})
VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

ANY_SCHEMA: dict[str, Any] = {}


def split_docstring(obj: Any) -> tuple[str, str]:
    raw = inspect.getdoc(obj) or ""
    if not raw:
        return "", ""
    head, _, tail = raw.partition("\n\n")
    summary = " ".join(head.split())
    return summary[:200], textwrap.dedent(tail).strip()


def _annotations(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        return get_type_hints(fn)
    except Exception:
        # Unresolvable forward refs are common in real code; an untyped schema beats
        # refusing to adapt the function at all.
        return {}


def input_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    hints = _annotations(fn)
    fields: dict[str, Any] = {}

    for name, param in inspect.signature(fn).parameters.items():
        if name in SKIP_PARAMS or param.kind in VARIADIC:
            continue
        annotation = hints.get(name, Any)
        default = ... if param.default is inspect.Parameter.empty else param.default
        try:
            TypeAdapter(annotation)
        except Exception:
            annotation = Any
        fields[name] = (annotation, default)

    if not fields:
        return dict(EMPTY_OBJECT_SCHEMA)

    model = create_model(f"{getattr(fn, '__name__', 'call')}_input", **fields)
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


def output_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    annotation = _annotations(fn).get("return", Any)
    if annotation is Any or annotation is None or annotation is type(None):
        return dict(ANY_SCHEMA)
    try:
        schema = TypeAdapter(annotation).json_schema()
    except Exception:
        return dict(ANY_SCHEMA)
    schema.pop("title", None)
    return schema


def affordance_kind(fn: Callable[..., Any]) -> AffordanceKind:
    """A generator is a stream. Nobody should have to declare that twice."""
    if inspect.isasyncgenfunction(fn) or inspect.isgeneratorfunction(fn):
        return AffordanceKind.STREAM
    return AffordanceKind.INVOKE


def is_async(fn: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)


def yields_type(fn: Callable[..., Any]) -> Any:
    """Element type of a generator's return annotation, if it declares one."""
    annotation = _annotations(fn).get("return", Any)
    args = getattr(annotation, "__args__", ())
    origin = getattr(annotation, "__origin__", None)
    if origin in {Iterator, AsyncIterator} or (args and origin is not None):
        return args[0] if args else Any
    return Any


def describe_callable(fn: Callable[..., Any], name: str | None = None) -> Affordance:
    summary, description = split_docstring(fn)
    kind = affordance_kind(fn)

    out = output_schema(fn)
    if kind is AffordanceKind.STREAM:
        element = yields_type(fn)
        try:
            out = TypeAdapter(element).json_schema() if element is not Any else dict(ANY_SCHEMA)
            out.pop("title", None)
        except Exception:
            out = dict(ANY_SCHEMA)

    return Affordance(
        name=(name or fn.__name__).lower(),
        summary=summary or f"Call {getattr(fn, '__name__', 'callable')}",
        description=description,
        kind=kind,
        input_schema=input_schema(fn),
        output_schema=out,
        determinism=Determinism.DETERMINISTIC,
        latency_class=LatencyClass.SECONDS,
        idempotent=True,
    )


def public_callables(obj: Any) -> dict[str, Callable[..., Any]]:
    """Public callables on a module or object, in declaration order where available."""
    found: dict[str, Callable[..., Any]] = {}
    for name, member in inspect.getmembers(obj, callable):
        if name.startswith("_") or inspect.isclass(member):
            continue
        if inspect.ismodule(obj) and getattr(member, "__module__", None) != obj.__name__:
            continue
        found[name] = member
    return found
