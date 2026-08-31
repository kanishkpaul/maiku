"""Observed liveness. The descriptor says how to check; this is what the check found."""

import time

from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    online: bool
    detail: str = ""
    latency_ms: float | None = None
    checked_at: float = Field(default_factory=time.time)

    @classmethod
    def up(cls, latency_ms: float | None = None) -> "Health":
        return cls(online=True, latency_ms=latency_ms)

    @classmethod
    def down(cls, detail: str) -> "Health":
        return cls(online=False, detail=detail)
