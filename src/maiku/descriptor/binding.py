"""How a participant is actually reached.

Separating *what it can do* (affordances) from *how you call it* (bindings) is the move
that lets one participant be reachable over several transports at once — the same model
served in-process to a local caller and over HTTP to a remote one.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maiku.descriptor.enums import Transport


class AuthRef(BaseModel):
    """A pointer to a credential, never the credential itself."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = "none"
    env_var: str | None = None
    header: str | None = None
    note: str = ""


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(pattern=r"^[a-z][a-z0-9_+-]*$")
    transport: Transport
    uri: str | None = None
    auth: AuthRef | None = None

    affordances: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    def serves(self, affordance: str) -> bool:
        return not self.affordances or affordance in self.affordances
