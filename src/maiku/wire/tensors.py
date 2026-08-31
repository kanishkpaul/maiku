"""Arrays on the wire, without knowing whose array it is.

numpy, torch, MLX and JAX all expose `.shape`, `.dtype` and a buffer; none of them need to
be imported to notice that. Duck-typing the array protocol rather than special-casing a
framework is what lets one code path serve every tensor participant, and it is why the
descriptor did not need a per-framework escape hatch.
"""

from typing import Any

from maiku.wire.parts import ArtifactRef, TensorPart

INLINE_LIMIT = 1024
"""Elements below which a tensor travels inside the message rather than as a file."""


def is_array(value: Any) -> bool:
    if isinstance(value, str | bytes | bytearray | dict):
        return False
    return hasattr(value, "shape") and hasattr(value, "dtype")


def dtype_name(value: Any) -> str:
    dtype = value.dtype
    return str(getattr(dtype, "name", dtype)).removeprefix("torch.")


def shape_of(value: Any) -> list[int]:
    return [int(d) for d in value.shape]


def element_count(value: Any) -> int:
    count = 1
    for dimension in shape_of(value):
        count *= dimension
    return count


def to_list(value: Any) -> Any:
    """Nested lists, going through whatever conversion the framework offers."""
    for attribute in ("tolist", "numpy"):
        method = getattr(value, attribute, None)
        if callable(method):
            converted = method()
            return converted.tolist() if hasattr(converted, "tolist") else converted
    return list(value)


def to_buffer(value: Any) -> bytes:
    for attribute in ("tobytes", "numpy"):
        method = getattr(value, attribute, None)
        if callable(method):
            converted = method()
            return converted if isinstance(converted, bytes) else converted.tobytes()
    return bytes(memoryview(value))


def to_part(value: Any, ref: ArtifactRef | None = None) -> TensorPart:
    """Inline when small, by reference when not.

    Both cases are real: a two-element probability vector inlines fine, a 512x512x3 image
    tensor must not, and a caller should not have to know which it is getting.
    """
    part = TensorPart(dtype=dtype_name(value), shape=shape_of(value))
    if ref is not None:
        part.ref = ref
    else:
        part.data = to_list(value)
    return part


def spills(value: Any, limit: int = INLINE_LIMIT) -> bool:
    return element_count(value) > limit
