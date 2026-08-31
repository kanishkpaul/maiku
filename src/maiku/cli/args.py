"""Turning shell arguments into call arguments."""

import json
from typing import Any


def parse_pair(pair: str) -> tuple[str, Any]:
    key, sep, raw = pair.partition("=")
    if not sep:
        raise ValueError(f"{pair!r} is not key=value")
    return key, coerce(raw)


def coerce(raw: str) -> Any:
    """JSON where it parses, string otherwise.

    So `--arg count=3` gives a number and `--arg name=3pm` gives a string, which is what
    someone typing at a shell means in both cases.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def collect(pairs: list[str], payload: str | None = None) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    if payload:
        loaded = json.loads(payload)
        if not isinstance(loaded, dict):
            raise ValueError("--json must be an object")
        arguments.update(loaded)
    arguments.update(dict(parse_pair(p) for p in pairs))
    return arguments
