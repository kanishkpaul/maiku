"""What a discoverer is, and what it may return.

Not called `probe`: that name is taken across the codebase for liveness checking, and one
word meaning two things is how a vocabulary starts rotting.

A discoverer reads what a thing already publishes about itself. It never infers capability
from an undocumented protocol, and where nothing is published it says what it tried.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import Kind
from maiku.descriptor.participant import Display, Provenance


class InvalidAddress(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Address:
    """Somewhere to look, before anything is known about what is there.

    Deliberately not a `ParticipantURI`: that names a scheme, and which scheme applies is
    the question discovery exists to answer.
    """

    raw: str
    url: str

    @classmethod
    def parse(cls, raw: str) -> "Address":
        text = raw.strip()
        if not text:
            raise InvalidAddress("an address cannot be empty")

        # Bare hosts get http rather than a guess between the two: an explicit
        # `auto:https://host` is one keystroke, and a silent upgrade would hide which
        # scheme actually answered.
        url = text if "://" in text else f"http://{text}"
        if not urlsplit(url).hostname:
            raise InvalidAddress(f"{raw!r} has no host")
        return cls(raw=raw, url=url.rstrip("/"))

    @property
    def netloc(self) -> str:
        return urlsplit(self.url).netloc

    def join(self, path: str) -> str:
        return f"{self.url}/{path.lstrip('/')}"

    @property
    def slug(self) -> str:
        """A handle-safe name for the address, so one address yields one handle."""
        cleaned = "".join(c if c.isalnum() else "-" for c in self.netloc.lower())
        return "-".join(part for part in cleaned.split("-") if part) or "device"

    def __str__(self) -> str:
        return self.url


@dataclass(frozen=True, slots=True)
class Attempt:
    """One thing that was tried and what came back.

    Kept as a pair rather than a formatted string because a failure has to be legible to
    an operator and countable by a test.
    """

    target: str
    outcome: str

    def __str__(self) -> str:
        return f"{self.target} -> {self.outcome}"


@dataclass(frozen=True, slots=True)
class Reading:
    """One discoverer's answer for one address. Not a descriptor.

    Only `assemble` makes descriptors; a reading that thought it was one would be a second
    participant for an address that has exactly one.
    """

    source: str
    affordances: Sequence[Affordance]
    binding: Binding
    kind: Kind | None = None
    display: Display | None = None
    provenance: Provenance | None = None
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)


class NotReadable(Exception):
    """A discoverer applied but could not read. Carries everything it tried."""

    def __init__(self, source: str, attempts: Sequence[Attempt]) -> None:
        self.source = source
        self.attempts = tuple(attempts)
        detail = "; ".join(str(a) for a in self.attempts) or "nothing was attempted"
        super().__init__(f"{source} could not read: {detail}")


@runtime_checkable
class Discoverer(Protocol):
    name: str
    precedence: int

    async def applies(self, address: Address) -> bool:
        """Cheap, non-mutating check. May do one read request, must never write."""

    async def read(self, address: Address) -> Reading:
        """Affordances plus one binding, or `NotReadable` naming what was tried."""
