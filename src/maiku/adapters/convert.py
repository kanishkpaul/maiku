"""Turning ordinary Python values into wire parts and JSON-safe results."""

from typing import Any

from maiku.adapters.context import ArtifactIO
from maiku.wire import tensors
from maiku.wire.parts import DataPart, Part, TensorPart, TextPart

TENSOR_MEDIA_TYPE = "application/x-maiku-tensor"


def to_part(value: Any) -> Part:
    if isinstance(value, str):
        return TextPart(text=value)
    if isinstance(value, TextPart | DataPart | TensorPart):
        return value
    if tensors.is_array(value):
        return tensors.to_part(value)
    return DataPart(data=value)


async def to_result(value: Any, artifacts: ArtifactIO | None = None) -> Any:
    """A JSON-safe view of whatever a participant returned.

    Arrays keep their dtype and shape either way; only the payload moves, spilling to an
    artifact once inlining it would bloat the message. The caller reads the same two fields
    regardless, so nothing downstream has to branch on size.
    """
    if not tensors.is_array(value):
        return value

    ref = None
    if tensors.spills(value) and artifacts is not None:
        ref = await artifacts.write(
            tensors.to_buffer(value),
            media_type=TENSOR_MEDIA_TYPE,
            name=f"{tensors.dtype_name(value)}{list(tensors.shape_of(value))}.bin",
        )
    return tensors.to_part(value, ref).model_dump(mode="json", exclude_none=True)


def collapse(chunks: list[Any]) -> Any:
    """Fold a stream back into one result.

    Text streams concatenate, because a caller that asked for a summary wants the summary,
    not a list of 400 fragments. Everything else keeps its shape.
    """
    if chunks and all(isinstance(c, str) for c in chunks):
        return "".join(chunks)
    return chunks
