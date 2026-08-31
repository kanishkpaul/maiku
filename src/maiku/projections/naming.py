"""Flattening handles into namespaces that only allow one identifier.

MCP tool names and OpenAI function names are single flat symbols, but a maiku affordance
is addressed by `handle` plus `affordance`. The mangling has to be reversible or a gateway
cannot route a call back to the participant that owns it.
"""

import re

SEPARATOR = "__"
_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def flatten(handle: str, affordance: str) -> str:
    return f"{_slug(handle)}{SEPARATOR}{_slug(affordance)}"


def unflatten(name: str) -> tuple[str, str]:
    """Recover (handle_slug, affordance). The handle is a slug, so resolve it via lookup."""
    handle, sep, affordance = name.rpartition(SEPARATOR)
    if not sep:
        raise ValueError(f"{name!r} is not a flattened maiku name")
    return handle, affordance


def _slug(value: str) -> str:
    return _UNSAFE.sub("_", value).strip("_")


def handle_slug(handle: str) -> str:
    return _slug(handle)
