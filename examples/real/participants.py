"""The trained CNN, as a participant.

Two ways to adapt the same model, on purpose. `torch:examples.real.cnn:DigitCNN` gives raw
tensor access through the generic adapter; this module gives it meaning - an image artifact
in, a labelled judgement out. Neither is more correct; they are different granularities of
the same thing, which is what a real adapter layer has to support.
"""

import io

import numpy as np
import torch

from examples.real import cnn
from maiku.adapters.context import CallContext
from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Determinism, Kind, LatencyClass, SideEffect
from maiku.descriptor.hints import artifact_schema

_model: cnn.DigitCNN | None = None
_samples = None

MEAN, STD = 0.1307, 0.3081


def _net() -> cnn.DigitCNN:
    global _model
    if _model is None:
        _model = cnn.load()
    return _model


def _testset():
    global _samples
    if _samples is None:
        from torchvision import datasets

        _samples = datasets.MNIST(cnn.DATA, train=False, download=False)
    return _samples


@participant(
    handle="local/digits",
    kind=Kind.MODEL,
    name="DigitCNN",
    description="A convolutional net trained on MNIST to 98% test accuracy",
    tags=["vision", "cnn", "pytorch", "classifier"],
)
@affordance(
    determinism=Determinism.DETERMINISTIC,
    latency_class=LatencyClass.INSTANT,
    idempotent=True,
    side_effects=SideEffect.READ,
    input_schema={
        "type": "object",
        "properties": {"image": artifact_schema("image/png", "A 28x28 greyscale digit")},
        "required": ["image"],
    },
)
async def classify(image: str, ctx: CallContext) -> dict:
    """Identify the handwritten digit in an image. Returns the digit and its confidence."""
    from PIL import Image

    raw = await ctx.artifacts.read(image)
    picture = Image.open(io.BytesIO(raw)).convert("L").resize((28, 28))
    pixels = (np.asarray(picture, dtype=np.float32) / 255.0 - MEAN) / STD

    with torch.no_grad():
        probabilities = _net()(torch.from_numpy(pixels)).softmax(dim=1)[0]

    best = int(probabilities.argmax())
    return {
        "digit": best,
        "confidence": round(float(probabilities[best]), 4),
        "runner_up": int(probabilities.argsort(descending=True)[1]),
    }


@affordance(
    latency_class=LatencyClass.INSTANT,
    side_effects=SideEffect.WRITE,
    determinism=Determinism.DETERMINISTIC,
)
async def sample_digit(index: int, ctx: CallContext) -> str:
    """Fetch a real image from the MNIST test set and store it. Returns its artifact digest."""
    picture, _label = _testset()[index % len(_testset())]
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    ref = await ctx.artifacts.write(
        buffer.getvalue(), media_type="image/png", name=f"mnist-test-{index}.png"
    )
    return ref.digest


@affordance(
    latency_class=LatencyClass.INSTANT,
    side_effects=SideEffect.NONE,
    determinism=Determinism.DETERMINISTIC,
)
def ground_truth(index: int) -> int:
    """The human-written label for an MNIST test image. Used to check the model, not to guide it."""
    return int(_testset()[index % len(_testset())][1])
