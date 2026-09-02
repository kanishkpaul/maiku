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
    "a2a": "maiku.adapters.a2a_client",
    "auto": "maiku.discovery.adapter",
    "cli": "maiku.adapters.cli_tool",
    "hf": "maiku.adapters.hf_pipeline",
    "http": "maiku.adapters.http_api",
    "human": "maiku.adapters.human",
    "mcp": "maiku.adapters.mcp_client",
    "lmstudio": "maiku.adapters.openai_compat",
    "ollama": "maiku.adapters.openai_compat",
    "openai": "maiku.adapters.openai_compat",
    "openrouter": "maiku.adapters.openai_compat",
    "python": "maiku.adapters.python_fn",
    "torch": "maiku.adapters.torch_model",
    "vllm": "maiku.adapters.openai_compat",
    "wiz": "maiku.adapters.wiz",
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


def coerce(raw: str) -> ParticipantURI:
    """Explicit `auto:` first, bare addresses only as sugar on top.

    Keeping the explicit form primary is what keeps `maiku add` honest: a mistyped scheme
    should say it is unknown, not quietly turn into a network address and fail later with
    a discovery error about a host that was never meant to be one.
    """
    try:
        uri = ParticipantURI.parse(raw)
    except InvalidURI:
        return _as_auto(raw)
    if uri.scheme == "http" and uri.target.startswith("//"):
        return _as_auto(raw)
    return uri if uri.scheme in known_schemes() else _as_auto(raw)


def looks_like_an_address(raw: str) -> bool:
    if "://" in raw:
        return True
    host, sep, port = raw.partition(":")
    if sep:
        return port.isdigit()
    return "." in host or host == "localhost"


def _as_auto(raw: str) -> ParticipantURI:
    if not looks_like_an_address(raw):
        scheme = raw.partition(":")[0]
        raise InvalidURI(
            f"no adapter for scheme {scheme!r}; known: {', '.join(known_schemes())}"
        )
    return ParticipantURI.parse(f"auto:{raw}")


async def open_participant(raw: str | ParticipantURI) -> "Adapter":
    uri = coerce(raw) if isinstance(raw, str) else raw
    return await resolve(uri).open(uri)
