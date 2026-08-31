"""Optional annotations for Python participants.

Inference gets most of a descriptor right. These decorators exist for the parts it cannot
know: that a function is stochastic, that it costs money, that it needs approval.
"""

from collections.abc import Callable
from typing import Any, TypeVar

MARKER = "__maiku__"

F = TypeVar("F", bound=Callable[..., Any])


def _slot(fn: Any, key: str) -> dict[str, Any]:
    meta = getattr(fn, MARKER, None)
    if meta is None:
        meta = {}
        setattr(fn, MARKER, meta)
    return meta.setdefault(key, {})


def participant(**overrides: Any) -> Callable[[F], F]:
    """Declare participant-level facts: handle, kind, display, permissions, runtime."""

    def wrap(fn: F) -> F:
        _slot(fn, "participant").update(overrides)
        return fn

    return wrap


def affordance(**overrides: Any) -> Callable[[F], F]:
    """Override inferred affordance fields for this callable."""

    def wrap(fn: F) -> F:
        _slot(fn, "affordance").update(overrides)
        return fn

    return wrap


def overrides_for(fn: Any, key: str) -> dict[str, Any]:
    return dict(getattr(fn, MARKER, {}).get(key, {}))
