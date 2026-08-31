"""A module exercising all four callable shapes an adapter must handle."""

import asyncio
from collections.abc import AsyncIterator, Iterator

from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Determinism, LatencyClass

__version__ = "1.2.3"


@participant(handle="test/sample", name="Sample", tags=["testing"])
def score(text: str, threshold: float = 0.5) -> float:
    """Score a string.

    Longer prose that belongs in the description rather than the summary.
    """
    return min(1.0, len(text) / 100 + threshold)


async def fetch(key: str) -> dict[str, str]:
    """Look something up asynchronously."""
    await asyncio.sleep(0)
    return {"key": key, "value": key.upper()}


@affordance(determinism=Determinism.STOCHASTIC, latency_class=LatencyClass.INSTANT)
def tokens(text: str) -> Iterator[str]:
    """Emit words one at a time."""
    yield from text.split()


async def narrate(count: int) -> AsyncIterator[str]:
    """Stream a countdown."""
    for i in range(count, 0, -1):
        await asyncio.sleep(0)
        yield f"{i} "


def _private(x: int) -> int:
    return x
