"""Participant URIs: `scheme:target[?k=v&...]`.

One addressable string per participant is the whole onboarding UX — `maiku add
ollama:qwen3:8b` has to be the entire ceremony, or nobody adapts anything.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import parse_qsl


class InvalidURI(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParticipantURI:
    scheme: str
    target: str
    params: Mapping[str, str]
    raw: str

    @classmethod
    def parse(cls, raw: str) -> "ParticipantURI":
        scheme, sep, rest = raw.partition(":")
        if not sep or not scheme:
            raise InvalidURI(f"{raw!r} is not scheme:target")
        if not scheme.replace("_", "").replace("-", "").isalnum():
            raise InvalidURI(f"{scheme!r} is not a usable scheme")

        target, params = rest, {}
        # Split on the last '?' only when it actually looks like a query, since targets
        # are frequently shell commands that contain their own punctuation.
        head, sep, tail = rest.rpartition("?")
        if sep and "=" in tail:
            target, params = head, dict(parse_qsl(tail))

        return cls(
            scheme=scheme.lower(),
            target=target,
            params=MappingProxyType(dict(params)),
            raw=raw,
        )

    def param(self, key: str, default: str | None = None) -> str | None:
        return self.params.get(key, default)

    def flag(self, key: str, default: bool = False) -> bool:
        value = self.params.get(key)
        return default if value is None else value.lower() in {"1", "true", "yes", "on"}

    def __str__(self) -> str:
        return self.raw
