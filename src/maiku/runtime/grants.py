"""Attenuated capability grants.

MCP, A2A and ACP can all say who an agent is; none of them can say "this participant may
call that affordance, on these artifacts, until Tuesday, and may pass on strictly less than
it holds". That gap is why delegation in agent systems is currently a matter of trust
rather than of evidence.

The rule is one line and it is the whole security model: a derived grant may only narrow.
"""

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maiku.descriptor.enums import SIDE_EFFECT_ORDER, SideEffect
from maiku.wire.task import new_id

WILDCARD = "*"
SEPARATOR = "#"


def scopes_satisfied(held: set[str], needed: set[str]) -> bool:
    return WILDCARD in held or needed <= held


class Escalation(PermissionError):
    """A derived grant tried to claim authority its parent did not hold."""


class Denied(PermissionError):
    pass


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    participant: str = WILDCARD
    affordance: str = WILDCARD

    @classmethod
    def parse(cls, value: "str | Capability") -> "Capability":
        if isinstance(value, Capability):
            return value
        participant, sep, affordance = value.partition(SEPARATOR)
        return cls(participant=participant, affordance=affordance if sep else WILDCARD)

    def covers(self, other: "Capability") -> bool:
        return self._matches(self.participant, other.participant) and self._matches(
            self.affordance, other.affordance
        )

    def matches(self, participant: str, affordance: str) -> bool:
        return self.covers(Capability(participant=participant, affordance=affordance))

    @staticmethod
    def _matches(pattern: str, value: str) -> bool:
        return pattern in (WILDCARD, value)

    def __str__(self) -> str:
        return f"{self.participant}{SEPARATOR}{self.affordance}"


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("grant"))
    issuer: str
    subject: str
    capabilities: list[Capability] = Field(default_factory=list)
    scopes: set[str] = Field(default_factory=set)
    artifacts: set[str] = Field(default_factory=set)
    max_side_effect: SideEffect = SideEffect.NONE
    expires_at: float | None = None
    parent_id: str | None = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at

    def covers(self, capability: Capability) -> bool:
        return any(mine.covers(capability) for mine in self.capabilities)

    def permits(
        self,
        participant: str,
        affordance: str,
        *,
        side_effect: SideEffect = SideEffect.NONE,
        scopes: set[str] | None = None,
    ) -> bool:
        if self.expired:
            return False
        if not self.covers(Capability(participant=participant, affordance=affordance)):
            return False
        if SIDE_EFFECT_ORDER[side_effect] > SIDE_EFFECT_ORDER[self.max_side_effect]:
            return False
        return scopes_satisfied(self.scopes, scopes or set())

    def check(
        self,
        participant: str,
        affordance: str,
        *,
        side_effect: SideEffect = SideEffect.NONE,
        scopes: set[str] | None = None,
    ) -> None:
        if not self.permits(participant, affordance, side_effect=side_effect, scopes=scopes):
            raise Denied(f"{self.subject} may not call {participant}{SEPARATOR}{affordance}")

    def attenuate(self, subject: str, **narrower: Any) -> "Grant":
        """Derive a child grant, refusing anything the parent does not already hold."""
        fields = self.model_dump(exclude={"id", "parent_id", "issuer", "subject"})
        fields.update(narrower)
        child = Grant(
            **fields,
            issuer=self.subject,
            subject=subject,
            parent_id=self.id,
        )
        assert_narrows(self, child)
        return child


def assert_narrows(parent: Grant, child: Grant) -> None:
    """The whole security model. A child may hold less than its parent, never more."""
    for capability in child.capabilities:
        if not parent.covers(capability):
            raise Escalation(f"{capability} exceeds {parent.id}")
    if not scopes_satisfied(parent.scopes, child.scopes):
        raise Escalation(f"scopes {sorted(child.scopes - parent.scopes)} exceed {parent.id}")
    if not child.artifacts <= parent.artifacts:
        raise Escalation(f"artifacts exceed {parent.id}")
    if SIDE_EFFECT_ORDER[child.max_side_effect] > SIDE_EFFECT_ORDER[parent.max_side_effect]:
        raise Escalation(f"side effect {child.max_side_effect} exceeds {parent.id}")
    if parent.expires_at is not None and (
        child.expires_at is None or child.expires_at > parent.expires_at
    ):
        raise Escalation(f"expiry exceeds {parent.id}")


def root_grant(subject: str, issuer: str = "user") -> Grant:
    """The unattenuated grant a human starts from. Everything else descends from this."""
    return Grant(
        issuer=issuer,
        subject=subject,
        capabilities=[Capability()],
        scopes={WILDCARD},
        max_side_effect=SideEffect.IRREVERSIBLE,
    )


def verify_chain(chain: list[Grant]) -> None:
    """Confirm a delegation chain only ever narrows, root first."""
    for parent, child in zip(chain, chain[1:], strict=False):
        if child.parent_id != parent.id:
            raise Escalation(f"{child.id} does not descend from {parent.id}")
        assert_narrows(parent, child)
