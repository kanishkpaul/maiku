"""Task lifecycle.

States are A2A's verbatim so the projection to an A2A task is a rename, not a mapping
with lossy corners. `input_required` and `auth_required` are interrupted rather than
terminal, which is what lets a human sit in the middle of a call.
"""

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskState(StrEnum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    AUTH_REQUIRED = "auth_required"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"


TERMINAL_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.CANCELED, TaskState.FAILED, TaskState.REJECTED}
)

INTERRUPTED_STATES = frozenset(
    {TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED, TaskState.APPROVAL_REQUIRED}
)


def is_terminal(state: TaskState) -> bool:
    return state in TERMINAL_STATES


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: TaskState = TaskState.SUBMITTED
    detail: str = ""
    at: float = Field(default_factory=time.time)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("task"))
    session_id: str
    participant: str
    affordance: str
    status: TaskStatus = Field(default_factory=TaskStatus)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    parent_task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def done(self) -> bool:
        return is_terminal(self.status.state)
