"""Scheme resolution.

Built-ins are listed by module path and imported only when their scheme is used, so
`import maiku` stays cheap even in an environment where torch is installed.
"""

import importlib
from typing import TYPE_CHECKING

from maiku.adapters.uri import InvalidURI, ParticipantURI

if TYPE_CHECKING:
    from maiku.adapters.base import Adapter

BUILTIN_SCHEMES: dict[str, str] = {
    "human": "maiku.adapters.human",
    "python": "maiku.adapters.python_fn",
}

_registered: dict[str, type["Adapter"]] = {}


def register(cls: type["Adapter"]) -> type["Adapter"]:
    _registered[cls.scheme] = cls
    return cls


def known_schemes() -> list[str]:
    return sorted(set(BUILTIN_SCHEMES) | set(_registered))


def resolve(uri: ParticipantURI) -> type["Adapter"]:
    if uri.scheme not in _registered and uri.scheme in BUILTIN_SCHEMES:
        importlib.import_module(BUILTIN_SCHEMES[uri.scheme])

    try:
        return _registered[uri.scheme]
    except KeyError:
        raise InvalidURI(
            f"no adapter for scheme {uri.scheme!r}; known: {', '.join(known_schemes())}"
        ) from None


async def open_participant(raw: str | ParticipantURI) -> "Adapter":
    uri = ParticipantURI.parse(raw) if isinstance(raw, str) else raw
    return await resolve(uri).open(uri)
