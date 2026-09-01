"""The ParticipantDescriptor: one document that makes any computing thing legible."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    Approval,
    Device,
    Kind,
    ProbeKind,
    Residency,
    SideEffect,
    max_side_effect,
)

SCHEMA_VERSION = "maiku/v0"

Handle = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._:-]*)+$")]


class Display(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    icon: str | None = None
    tags: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    """Where this participant came from and who adapted it.

    Carries no timestamps: the descriptor must hash identically across runs, so
    "when did we first see this" belongs to the registry, not the document.
    """

    model_config = ConfigDict(extra="forbid")

    vendor: str = ""
    version: str = ""
    license: str = ""
    source_uri: str | None = None
    adapter: str = ""
    adapter_version: str = ""


class Resources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ram_gb: float | None = None
    vram_gb: float | None = None


class Cost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: str
    amount: float
    currency: str = "USD"


class RuntimeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    residency: Residency
    host: str | None = None
    device: Device = Device.NONE
    resources: Resources = Field(default_factory=Resources)
    cold_start_ms: int | None = None
    max_concurrency: int = 1
    cost: Cost | None = None


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProbeKind = ProbeKind.ADAPTER
    target: str | None = None
    interval_s: int = 30
    timeout_s: float = 5.0


class Liveness(BaseModel):
    """How to find out whether the thing is up. Observed state lives in the registry."""

    model_config = ConfigDict(extra="forbid")

    probe: Probe = Field(default_factory=Probe)
    ttl_s: int = 60


class IODefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    output_modes: list[str] = Field(default_factory=lambda: ["text/plain"])


class ArtifactPolicy(BaseModel):
    """What files this participant can take in and hand back. Media types may wildcard."""

    model_config = ConfigDict(extra="forbid")

    can_read: list[str] = Field(default_factory=list)
    can_write: list[str] = Field(default_factory=list)
    max_bytes: int | None = None


class Permissions(BaseModel):
    """Two directions that are easy to conflate.

    `scopes_required` is what this participant needs *from* the runtime to do its job.
    `scopes_offered` is what a caller must already hold to be allowed to call it.
    """

    model_config = ConfigDict(extra="forbid")

    scopes_required: list[str] = Field(default_factory=list)
    scopes_offered: list[str] = Field(default_factory=list)
    side_effects: SideEffect = SideEffect.NONE
    approval: Approval = Approval.NEVER
    egress: list[str] = Field(default_factory=list)
    filesystem: list[str] = Field(default_factory=list)


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alg: str
    key_id: str
    value: str


class ParticipantDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["maiku/v0"] = SCHEMA_VERSION
    handle: Handle
    kind: Kind
    display: Display
    provenance: Provenance = Field(default_factory=Provenance)
    runtime: RuntimeInfo
    affordances: list[Affordance] = Field(min_length=1)
    bindings: list[Binding] = Field(min_length=1)
    io_defaults: IODefaults = Field(default_factory=IODefaults)
    artifacts: ArtifactPolicy = Field(default_factory=ArtifactPolicy)
    permissions: Permissions = Field(default_factory=Permissions)
    liveness: Liveness = Field(default_factory=Liveness)
    extensions: dict[str, Any] = Field(default_factory=dict)
    signature: Signature | None = None

    @field_validator("affordances")
    @classmethod
    def _unique_affordance_names(cls, value: list[Affordance]) -> list[Affordance]:
        names = [a.name for a in value]
        if len(names) != len(set(names)):
            raise ValueError("affordance names must be unique within a participant")
        return value

    @model_validator(mode="wrap")
    @classmethod
    def _verify_declared_id(cls, data: Any, handler: Any) -> "ParticipantDescriptor":
        """Accept a serialized descriptor back, and check its hash while we are here.

        `id` is derived, so it cannot be an input field — but a document that cannot be
        read back is not a document format. Popping it turns every load into a free
        tamper check: a descriptor whose declared id no longer matches its capabilities
        has been edited in transit.
        """
        declared: str | None = None
        if isinstance(data, dict) and "id" in data:
            declared = data["id"]
            data = {k: v for k, v in data.items() if k != "id"}
        instance = handler(data)
        if declared is not None and declared != instance.id:
            raise ValueError(
                f"declared id {declared!r} does not match content hash {instance.id!r}"
            )
        return instance

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        from maiku.descriptor.canonical import content_id

        return content_id(self)

    @property
    def capability_id(self) -> str:
        """What this affords, with the handle taken out.

        Never serialized: it is derivable from the document, and a second id on the wire
        would be a second thing to keep honest.
        """
        from maiku.descriptor.canonical import capability_id

        return capability_id(self)

    def affordance(self, name: str) -> Affordance:
        for a in self.affordances:
            if a.name == name:
                return a
        raise KeyError(f"{self.handle} has no affordance {name!r}")

    def binding_for(self, affordance: str) -> Binding:
        for b in self.bindings:
            if b.serves(affordance):
                return b
        raise KeyError(f"{self.handle} has no binding serving {affordance!r}")

    @property
    def worst_side_effect(self) -> SideEffect:
        return max_side_effect([a.side_effects for a in self.affordances])
