"""The one event vocabulary every adapter emits.

This is the load-bearing abstraction. A video model, a coding agent and a person answering
a question have nothing in common at the call site — but they can all be described as a
stream of these events, and that is what makes them commensurable to the runtime.

Invariant, enforced by the conformance suite: a stream emits exactly one terminal event
(`Finished` or `Failed`) and it is last.
"""

import time
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from maiku.wire.parts import ArtifactRef, Part
from maiku.wire.task import TaskState


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal: ClassVar[bool] = False

    # Stamped by the router, not the adapter: an adapter that had to track ordering would
    # be reimplementing the bus every time someone writes one.
    seq: int = -1
    at: float = Field(default_factory=time.time)


class Started(_Event):
    type: Literal["started"] = "started"
    participant: str
    affordance: str


class Progress(_Event):
    type: Literal["progress"] = "progress"
    message: str = ""
    fraction: float | None = Field(default=None, ge=0.0, le=1.0)


class Delta(_Event):
    """One increment of output. Streaming text, a generated frame, a partial tensor."""

    type: Literal["delta"] = "delta"
    part: Part
    index: int = 0


class ArtifactWritten(_Event):
    type: Literal["artifact_written"] = "artifact_written"
    ref: ArtifactRef
    role: str = "output"


class NeedsInput(_Event):
    type: Literal["needs_input"] = "needs_input"
    request_id: str
    prompt: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class NeedsApproval(_Event):
    type: Literal["needs_approval"] = "needs_approval"
    request_id: str
    reason: str
    side_effects: str = "none"
    detail: dict[str, Any] = Field(default_factory=dict)


class Log(_Event):
    type: Literal["log"] = "log"
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str


class Usage(_Event):
    """What the call consumed, in whatever unit the participant actually bills in."""

    type: Literal["usage"] = "usage"
    unit: str = "call"
    amount: float = 1.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: float | None = None
    cost: float | None = None
    currency: str = "USD"


class Finished(_Event):
    """Terminal success.

    `result` is plain JSON validated against the affordance's output_schema; artifacts
    appear inside it as digest strings. Keeping one typed result rather than a parallel
    bag of parts means a caller never has to ask which representation is authoritative.
    """

    type: Literal["finished"] = "finished"
    terminal: ClassVar[bool] = True

    state: TaskState = TaskState.COMPLETED
    result: Any = None


class Failed(_Event):
    type: Literal["failed"] = "failed"
    terminal: ClassVar[bool] = True

    code: str = "adapter_error"
    message: str
    retryable: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)


Event = Annotated[
    Started
    | Progress
    | Delta
    | ArtifactWritten
    | NeedsInput
    | NeedsApproval
    | Log
    | Usage
    | Finished
    | Failed,
    Field(discriminator="type"),
]

TERMINAL_EVENTS: tuple[type[_Event], ...] = (Finished, Failed)


def is_terminal(event: _Event) -> bool:
    return type(event).terminal
