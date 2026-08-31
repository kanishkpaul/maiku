"""Payload vocabulary shared by every participant.

A2A's text/data/file triad covers agents talking to agents. It does not cover a
classifier handing a logit array to a scorer, so `TensorPart` is the one extension we
make: without it every non-chatbot has to smuggle numbers through JSON or base64 text.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ArtifactRef(BaseModel):
    """A pointer into the artifact store. Never the bytes themselves.

    Passing references instead of payloads is what keeps a 200 MB video out of a message
    log, and what makes per-participant access grants expressible at all.
    """

    model_config = ConfigDict(extra="forbid")

    digest: Digest
    media_type: str = "application/octet-stream"
    name: str | None = None
    size: int | None = None
    uri: str | None = None


class TextPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["data"] = "data"
    data: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilePart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"] = "file"
    ref: ArtifactRef
    metadata: dict[str, Any] = Field(default_factory=dict)


class TensorPart(BaseModel):
    """Numeric array, inline when small and by reference when not.

    The split exists because both cases are real: a 2-element probability vector inlines
    fine, a 512x512x3 image tensor must not.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tensor"] = "tensor"
    dtype: str
    shape: list[int]
    data: Any = None
    ref: ArtifactRef | None = None
    layout: Literal["row_major", "column_major"] = "row_major"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def inline(self) -> bool:
        return self.ref is None


Part = Annotated[
    TextPart | DataPart | FilePart | TensorPart,
    Field(discriminator="kind"),
]
