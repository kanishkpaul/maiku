import pytest

from maiku.descriptor import (
    Affordance,
    AffordanceKind,
    Binding,
    Determinism,
    Device,
    Display,
    Example,
    Kind,
    LatencyClass,
    ParticipantDescriptor,
    Provenance,
    Residency,
    RuntimeInfo,
    SideEffect,
    Transport,
)
from maiku.runtime.grants import Grant, root_grant


def make_descriptor(**overrides) -> ParticipantDescriptor:
    base = dict(
        handle="local/sentiment",
        kind=Kind.MODEL,
        display=Display(name="Sentiment", description="Binary sentiment classifier"),
        provenance=Provenance(vendor="hf", adapter="hf_pipeline", adapter_version="0.0.1"),
        runtime=RuntimeInfo(residency=Residency.IN_PROCESS, device=Device.MPS),
        affordances=[
            Affordance(
                name="classify",
                summary="Label a sentence positive or negative",
                kind=AffordanceKind.INVOKE,
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "label": {"enum": ["POSITIVE", "NEGATIVE"]},
                        "score": {"type": "number"},
                    },
                },
                examples=[Example(input={"text": "i love it"}, output={"label": "POSITIVE"})],
                determinism=Determinism.DETERMINISTIC,
                latency_class=LatencyClass.INSTANT,
                idempotent=True,
                side_effects=SideEffect.NONE,
            )
        ],
        bindings=[Binding(scheme="hf", transport=Transport.IN_PROCESS)],
    )
    base.update(overrides)
    return ParticipantDescriptor(**base)


@pytest.fixture
def descriptor() -> ParticipantDescriptor:
    return make_descriptor()


def everything(subject: str = "test") -> Grant:
    """The operator's own grant. A description made under it is the whole participant."""
    return root_grant(subject)


@pytest.fixture
def root() -> Grant:
    return everything()
