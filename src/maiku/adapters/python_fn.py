"""Adapt a Python function, object or module.

The zero-friction on-ramp, and the substrate the ML adapters build on. A module becomes a
multi-affordance participant, which is usually what people actually mean when they say
"expose my library".
"""

import asyncio
import importlib
import inspect
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, InvalidArguments, UnknownAffordance
from maiku.adapters.context import CallContext
from maiku.adapters.convert import collapse, to_part
from maiku.adapters.decorator import overrides_for
from maiku.adapters.introspect import (
    context_params,
    describe_callable,
    public_callables,
    split_docstring,
)
from maiku.adapters.registry import register
from maiku.adapters.uri import InvalidURI, ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import AffordanceKind, Kind, Residency, Transport
from maiku.descriptor.participant import (
    Display,
    ParticipantDescriptor,
    Provenance,
    RuntimeInfo,
)
from maiku.wire.events import Delta, Event, Finished

_SENTINEL = object()


def import_target(target: str) -> tuple[Any, str]:
    """Resolve `pkg.module` or `pkg.module:attr.path` to an object and a short name."""
    module_path, _, attr_path = target.partition(":")
    if not module_path:
        raise InvalidURI(f"python target {target!r} has no module")

    # Someone standing in their project root expects their own modules to import. The
    # installed console script does not put cwd on the path, so put it there.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        obj: Any = importlib.import_module(module_path)
    except ImportError as exc:
        raise AdapterError(f"cannot import {module_path!r}: {exc}") from exc

    name = module_path.rsplit(".", 1)[-1]
    for attr in filter(None, attr_path.split(".")):
        try:
            obj = getattr(obj, attr)
        except AttributeError as exc:
            raise AdapterError(f"{module_path!r} has no attribute {attr!r}") from exc
        name = attr

    return obj, name


def _bound_callables(obj: Any) -> dict[str, Callable[..., Any]]:
    if inspect.isclass(obj):
        obj = obj()
    if callable(obj) and not inspect.ismodule(obj):
        return {getattr(obj, "__name__", "call").lower(): obj}
    return {name.lower(): fn for name, fn in public_callables(obj).items()}


async def _aiter(fn: Callable[..., Any], arguments: dict[str, Any]) -> AsyncIterator[Any]:
    """Uniform async iteration over the four shapes a Python callable can take.

    Sync work goes to a thread: a blocking forward pass on the event loop would stall
    every other participant in the session.
    """
    if inspect.isasyncgenfunction(fn):
        async for item in fn(**arguments):
            yield item
    elif inspect.iscoroutinefunction(fn):
        yield await fn(**arguments)
    elif inspect.isgeneratorfunction(fn):
        gen = fn(**arguments)
        while (item := await asyncio.to_thread(next, gen, _SENTINEL)) is not _SENTINEL:
            yield item
    else:
        yield await asyncio.to_thread(lambda: fn(**arguments))


@register
class PythonAdapter(Adapter):
    scheme = "python"

    def __init__(self, uri: ParticipantURI, obj: Any, name: str) -> None:
        self._uri = uri
        self._obj = obj
        self._name = name
        self._callables = _bound_callables(obj)
        if not self._callables:
            raise AdapterError(f"{uri.target!r} exposes no public callables")

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "PythonAdapter":
        obj, name = import_target(uri.target)
        return cls(uri, obj, name)

    async def describe(self) -> ParticipantDescriptor:
        affordances: list[Affordance] = []
        participant_meta: dict[str, Any] = {}

        for name, fn in self._callables.items():
            base = describe_callable(fn, name=name)
            affordances.append(base.model_copy(update=overrides_for(fn, "affordance")))
            participant_meta.update(overrides_for(fn, "participant"))

        summary, description = split_docstring(self._obj)
        handle = participant_meta.pop("handle", None) or f"python/{self._name}"

        descriptor = ParticipantDescriptor(
            handle=handle,
            kind=participant_meta.pop("kind", Kind.TOOL),
            display=Display(
                name=participant_meta.pop("name", self._name),
                description=participant_meta.pop("description", summary or description),
                tags=participant_meta.pop("tags", []),
            ),
            provenance=Provenance(
                source_uri=self._uri.raw,
                adapter=self.scheme,
                adapter_version=self.version,
                version=getattr(self._obj, "__version__", ""),
            ),
            runtime=RuntimeInfo(residency=Residency.IN_PROCESS, host="localhost"),
            affordances=affordances,
            bindings=[Binding(scheme=self.scheme, transport=Transport.IN_PROCESS)],
        )
        return descriptor.model_copy(update=participant_meta) if participant_meta else descriptor

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        fn = self._callables.get(affordance)
        if fn is None:
            raise UnknownAffordance(f"{affordance!r} not in {sorted(self._callables)}")

        call_args = dict(arguments) | dict.fromkeys(context_params(fn), ctx)
        try:
            inspect.signature(fn).bind(**call_args)
        except TypeError as exc:
            raise InvalidArguments(str(exc)) from exc

        streaming = describe_callable(fn, name=affordance).kind is AffordanceKind.STREAM
        chunks: list[Any] = []
        index = 0

        async for item in _aiter(fn, call_args):
            ctx.raise_if_cancelled()
            chunks.append(item)
            if streaming:
                yield Delta(part=to_part(item), index=index)
                index += 1

        yield Finished(result=collapse(chunks) if streaming else chunks[-1] if chunks else None)
