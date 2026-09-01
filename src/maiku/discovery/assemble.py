"""One address, one descriptor.

Several discoverers may answer for a single address. They contribute to one descriptor in
progress; none of them produces a competing descriptor to be reconciled afterwards, so
there is never a moment where one address has two participants.

    address
       |
       +-- applies()?  ---> openapi   mcp   ...        (concurrent, non-mutating)
       |                       |       |
       +-- read()     --->  Reading  Reading           (a failure here is recorded,
       |                       |       |                not fatal)
       |                       v       v
       |                  sort by precedence, highest first
       |                          |
       |          +---------------+---------------+
       |          |               |               |
       |     bindings          affordances      hints
       |      union            merge by name     kind / display / provenance
       |          |               |               |
       |          |         same name, same schema -> keep one
       |          |         same name, other schema -> higher precedence wins,
       |          |                                    loser recorded verbatim
       |          |               |               |
       |          +---------------+---------------+
       |                          |
       +-- handle chosen once ----+
                                  |
                                  v
                       one ParticipantDescriptor

Nothing here reconciles two schemas into a third. Inventing a type nobody published is how
a registry starts lying.
"""

import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import Kind
from maiku.descriptor.participant import (
    Display,
    ParticipantDescriptor,
    Provenance,
    Residency,
    RuntimeInfo,
)
from maiku.discovery.base import Address, Attempt, Discoverer, NotReadable, Reading

EXTENSION_KEY = "maiku.discovery"
HANDLE_NAMESPACE = "auto"


@dataclass(frozen=True, slots=True)
class Skipped:
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class Discovery:
    """What one run found, and everything it could not read.

    Failures live here rather than on the descriptor: which readers happened to be up is
    a fact about the run, and folding it into the document would make the same address
    hash differently on a day one service was restarting.
    """

    descriptor: ParticipantDescriptor
    sources: tuple[str, ...]
    failures: tuple[NotReadable, ...]
    skipped: tuple[Skipped, ...]


class NothingReadable(Exception):
    """No discoverer could read the address, with every one of them named."""

    def __init__(
        self, address: Address, failures: Sequence[NotReadable], skipped: Sequence[Skipped]
    ) -> None:
        self.address = address
        self.failures = tuple(failures)
        self.skipped = tuple(skipped)
        lines = [f"nothing at {address} could be read"]
        lines += [f"  {f.source}: {'; '.join(str(a) for a in f.attempts)}" for f in self.failures]
        lines += [f"  {s.source}: {s.reason}" for s in self.skipped]
        super().__init__("\n".join(lines))


async def discover(
    address: Address,
    discoverers: Iterable[Discoverer],
    handle: str | None = None,
) -> Discovery:
    ordered = sorted(discoverers, key=lambda d: d.precedence, reverse=True)
    applicable, skipped = await _which_apply(ordered, address)
    readings, failures = await _read_all(applicable, address)

    if not readings:
        raise NothingReadable(address, failures, skipped)

    affordances, conflicts, served = merge_affordances(readings)
    return Discovery(
        descriptor=ParticipantDescriptor(
            handle=handle or f"{HANDLE_NAMESPACE}/{address.slug}",
            kind=_first(r.kind for r in readings) or Kind.SERVICE,
            display=_first(r.display for r in readings) or Display(name=address.slug),
            provenance=_provenance(address, readings),
            runtime=RuntimeInfo(residency=Residency.REMOTE, host=address.url),
            affordances=affordances,
            bindings=[_binding(r, served) for r in readings],
            extensions={EXTENSION_KEY: {"conflicts": conflicts}} if conflicts else {},
        ),
        sources=tuple(r.source for r in readings),
        failures=tuple(failures),
        skipped=tuple(skipped),
    )


def merge_affordances(
    readings: Sequence[Reading],
) -> tuple[list[Affordance], list[dict[str, Any]], dict[str, list[str]]]:
    """Merge by name, highest precedence first. Readings arrive already sorted.

    A losing schema is recorded whole rather than summarised: an operator resolving a
    disagreement needs the thing that lost, not a description of it. The loser also stops
    claiming to serve that affordance, since the merged schema is not one it accepts.
    """
    kept: dict[str, Affordance] = {}
    winner: dict[str, str] = {}
    served: dict[str, list[str]] = {r.source: [] for r in readings}
    conflicts: list[dict[str, Any]] = []

    for reading in readings:
        for affordance in reading.affordances:
            existing = kept.get(affordance.name)
            if existing is None:
                kept[affordance.name] = affordance
                winner[affordance.name] = reading.source
                served[reading.source].append(affordance.name)
            elif _same_shape(existing, affordance):
                served[reading.source].append(affordance.name)
            else:
                conflicts.append(
                    {
                        "affordance": affordance.name,
                        "kept": winner[affordance.name],
                        "discarded_source": reading.source,
                        "discarded": affordance.model_dump(mode="json"),
                    }
                )
    return list(kept.values()), conflicts, served


def _binding(reading: Reading, served: dict[str, list[str]]) -> Binding:
    """Name what this endpoint actually serves, so a call reaches the reader that won it.

    An empty list means "serves everything" to `Binding.serves`, so it is left empty only
    when the source really does serve every affordance it read.
    """
    names = served.get(reading.source) or []
    return reading.binding.model_copy(update={"affordances": names})


def _same_shape(left: Affordance, right: Affordance) -> bool:
    return left.input_schema == right.input_schema and left.output_schema == right.output_schema


async def _which_apply(
    discoverers: Sequence[Discoverer], address: Address
) -> tuple[list[Discoverer], list[Skipped]]:
    answers = await asyncio.gather(
        *(d.applies(address) for d in discoverers), return_exceptions=True
    )
    applicable, skipped = [], []
    for discoverer, answer in zip(discoverers, answers, strict=True):
        if isinstance(answer, BaseException):
            # A discoverer that raises here is broken, not inapplicable. Say which.
            skipped.append(Skipped(discoverer.name, f"applies() raised {answer!r}"))
        elif answer:
            applicable.append(discoverer)
        else:
            skipped.append(Skipped(discoverer.name, "does not apply to this address"))
    return applicable, skipped


async def _read_all(
    discoverers: Sequence[Discoverer], address: Address
) -> tuple[list[Reading], list[NotReadable]]:
    results = await asyncio.gather(
        *(d.read(address) for d in discoverers), return_exceptions=True
    )
    readings, failures = [], []
    for discoverer, result in zip(discoverers, results, strict=True):
        if isinstance(result, Reading):
            readings.append(result)
        elif isinstance(result, NotReadable):
            failures.append(result)
        else:
            failures.append(NotReadable(discoverer.name, [Attempt(address.url, repr(result))]))
    return readings, failures


def _provenance(address: Address, readings: Sequence[Reading]) -> Provenance:
    """Records every discoverer that contributed, so a descriptor can say how it was read.

    In provenance rather than extensions because provenance sits outside identity: which
    readers answered must not change what the participant is.
    """
    hint = _first(r.provenance for r in readings) or Provenance()
    return hint.model_copy(
        update={
            "source_uri": address.url,
            "adapter": f"discovery({'+'.join(r.source for r in readings)})",
        }
    )


def _first(values: Iterable[Any]) -> Any:
    return next((v for v in values if v is not None), None)


__all__ = ["Discovery", "NothingReadable", "Skipped", "discover", "merge_affordances"]
