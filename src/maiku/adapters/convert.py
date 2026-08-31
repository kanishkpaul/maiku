"""Turning ordinary Python values into wire parts."""

from typing import Any

from maiku.wire.parts import DataPart, Part, TextPart


def to_part(value: Any) -> Part:
    if isinstance(value, str):
        return TextPart(text=value)
    if isinstance(value, Part | TextPart | DataPart):
        return value  # type: ignore[return-value]
    return DataPart(data=value)


def collapse(chunks: list[Any]) -> Any:
    """Fold a stream back into one result.

    Text streams concatenate, because a caller that asked for a summary wants the summary,
    not a list of 400 fragments. Everything else keeps its shape.
    """
    if chunks and all(isinstance(c, str) for c in chunks):
        return "".join(chunks)
    return chunks
