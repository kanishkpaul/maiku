"""A single thing a participant can do."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maiku.descriptor.enums import (
    AffordanceKind,
    AffordanceOperation,
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
    operation: AffordanceOperation | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

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

    @model_validator(mode="after")
    def _operation_matches_kind(self) -> "Affordance":
        allowed = {
            AffordanceKind.INVOKE: {None, AffordanceOperation.INVOKE},
            AffordanceKind.STREAM: {None, AffordanceOperation.INVOKE},
            AffordanceKind.PROPERTY: {
                AffordanceOperation.READ,
                AffordanceOperation.WRITE,
            },
            AffordanceKind.EVENT: {AffordanceOperation.SUBSCRIBE},
        }
        if self.operation not in allowed[self.kind]:
            expected = ", ".join(
                sorted(operation.value for operation in allowed[self.kind] if operation is not None)
            )
            raise ValueError(
                f"{self.kind.value} affordance operation must be {expected or 'invoke'}"
            )
        return self

    @property
    def resolved_operation(self) -> AffordanceOperation:
        return self.operation or AffordanceOperation.INVOKE

    @property
    def streaming(self) -> bool:
        return self.kind in {AffordanceKind.STREAM, AffordanceKind.EVENT}
