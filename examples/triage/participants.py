"""The demo's own participants.

Deliberately not chatbots. A frame extractor produces files, a classifier produces tensors,
a scorer produces JSON, and a publisher has irreversible side effects and says so.
"""

import numpy as np

from maiku.adapters.context import CallContext
from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Approval, Determinism, Kind, LatencyClass, SideEffect
from maiku.descriptor.hints import artifact_schema
from maiku.descriptor.participant import Permissions

LABELS = ("empty", "motion", "person")
FRAME_BYTES = 66


@participant(
    handle="demo/vision",
    kind=Kind.MODEL,
    name="Frame triage",
    tags=["vision", "classifier", "demo"],
    permissions=Permissions(approval=Approval.ON_SCOPE, side_effects=SideEffect.IRREVERSIBLE),
)
@affordance(latency_class=LatencyClass.SECONDS, side_effects=SideEffect.WRITE)
async def extract_frames(clip: str, count: int, ctx: CallContext) -> list[str]:
    """Split a clip into frames, returning one artifact digest per frame."""
    source = await ctx.artifacts.read(clip)
    window = FRAME_BYTES // len(LABELS)
    digests = []

    for index in range(count):
        # A bright band that moves between windows, so the classifier has something to see.
        band = (index * 2) % len(LABELS)

        def pixel(offset: int, index: int = index, band: int = band) -> int:
            noise = source[(offset + index) % len(source)] % 60
            return min(255, noise + (170 if offset // window == band else 0))

        frame = bytes(pixel(offset) for offset in range(FRAME_BYTES))
        ref = await ctx.artifacts.write(frame, media_type="image/x-raw", name=f"frame{index}.raw")
        digests.append(ref.digest)
    return digests


@affordance(
    determinism=Determinism.DETERMINISTIC,
    latency_class=LatencyClass.INSTANT,
    side_effects=SideEffect.READ,
    input_schema={
        "type": "object",
        "properties": {"frame": artifact_schema("image/x-raw")},
        "required": ["frame"],
    },
)
async def classify(frame: str, ctx: CallContext) -> np.ndarray:
    """Score one frame, returning a logit per label. Tensors in, tensors out."""
    pixels = np.frombuffer(await ctx.artifacts.read(frame), dtype=np.uint8).astype(np.float32)
    usable = len(pixels) - len(pixels) % len(LABELS)  # frames arrive from outside; trim
    return pixels[:usable].reshape(len(LABELS), -1).mean(axis=1)


@affordance(determinism=Determinism.DETERMINISTIC, side_effects=SideEffect.NONE)
def tally(logits: list[list[float]]) -> dict:
    """Turn a batch of logits into a verdict. No model, no prompt, just arithmetic."""
    labels = [LABELS[int(np.argmax(row))] for row in logits]
    counts = {label: labels.count(label) for label in LABELS}
    return {
        "frames": len(labels),
        "counts": counts,
        "verdict": max(counts, key=counts.get),
        "sequence": labels,
    }


@affordance(
    latency_class=LatencyClass.SECONDS,
    side_effects=SideEffect.IRREVERSIBLE,
    scopes=["publish"],
    idempotent=False,
)
async def publish(summary: str, ctx: CallContext) -> str:
    """Write the report somewhere permanent. Gated, because it cannot be undone."""
    ref = await ctx.artifacts.write(
        summary.encode(), media_type="text/markdown", name="triage-report.md"
    )
    return ref.digest
