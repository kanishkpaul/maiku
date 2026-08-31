"""A single thing a participant can do."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from maiku.descriptor.enums import (
    AffordanceKind,
    Determinism,
    LatencyClass,
    SideEffect,
)

AffordanceName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]

EMPTY_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class Example(BaseModel):
    """A worked call.

    Examples carry the meaning that JSON Schema cannot. Twenty years of semantic web
    service research says automatic capability matching from types alone does not work;
    a concrete input/output pair is what lets a planner tell `classify` from `classify`.
    """

    model_config = ConfigDict(extra="forbid")

    input: Any = None
    output: Any = None
    note: str = ""


class Affordance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: AffordanceName
    summary: str = Field(max_length=200)
    description: str = ""
    kind: AffordanceKind = AffordanceKind.INVOKE

    input_schema: dict[str, Any] = Field(default_factory=lambda: dict(EMPTY_OBJECT_SCHEMA))
    output_schema: dict[str, Any] = Field(default_factory=lambda: dict(EMPTY_OBJECT_SCHEMA))
    examples: list[Example] = Field(default_factory=list)

    determinism: Determinism = Determinism.STOCHASTIC
    latency_class: LatencyClass = LatencyClass.SECONDS
    idempotent: bool = False
    side_effects: SideEffect = SideEffect.NONE
    cancellable: bool = True

    scopes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def streaming(self) -> bool:
        return self.kind is AffordanceKind.STREAM
