"""A classifier and an image model. No chat anywhere.

This is the falsification fixture: if the descriptor needs a special case for tensor and
file I/O, it fails here rather than after twelve adapters have been written against it.
"""

import numpy as np

from maiku.adapters.context import CallContext
from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Determinism, Kind, LatencyClass
from maiku.descriptor.hints import artifact_schema

LABELS = ["cat", "dog", "neither"]


@participant(handle="local/vision", kind=Kind.MODEL, tags=["vision", "classifier"])
@affordance(determinism=Determinism.DETERMINISTIC, latency_class=LatencyClass.INSTANT)
def logits(pixels: list[float]) -> np.ndarray:
    """Score an image, returning one logit per label."""
    total = sum(pixels) or 1.0
    return np.array([total % 3, total % 5, total % 7], dtype=np.float32)


@affordance(determinism=Determinism.DETERMINISTIC)
def embed(text: str) -> np.ndarray:
    """Produce an embedding large enough that inlining it would be rude."""
    seed = sum(ord(c) for c in text)
    return np.arange(seed, seed + 4096, dtype=np.float32).reshape(64, 64)


@affordance(
    input_schema={
        "type": "object",
        "properties": {"image": artifact_schema("image/png")},
        "required": ["image"],
    }
)
async def classify_file(image: str, ctx: CallContext) -> dict:
    """Read an image artifact and label it, taking bytes in and JSON out."""
    raw = await ctx.artifacts.read(image)
    index = len(raw) % len(LABELS)
    return {"label": LABELS[index], "confidence": round(0.5 + index / 10, 2)}


@affordance(latency_class=LatencyClass.SECONDS)
async def render(width: int, height: int, ctx: CallContext) -> str:
    """Generate an image and hand back a reference to it, never the bytes."""
    frame = np.full((height, width, 3), 128, dtype=np.uint8)
    ref = await ctx.artifacts.write(
        frame.tobytes(), media_type="image/x-raw", name=f"{width}x{height}.raw"
    )
    return ref.digest
