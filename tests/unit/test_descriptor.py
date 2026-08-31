import pytest
from pydantic import ValidationError

from maiku.descriptor import (
    Affordance,
    ParticipantDescriptor,
    Residency,
    RuntimeInfo,
    SideEffect,
    canonical_json,
    content_id,
)
from tests.conftest import make_descriptor


def test_id_is_content_addressed_and_stable(descriptor):
    assert descriptor.id.startswith("mk:")
    assert descriptor.id == make_descriptor().id


def test_id_ignores_where_it_runs(descriptor):
    moved = make_descriptor(runtime=RuntimeInfo(residency=Residency.REMOTE, host="gpu-box.local"))
    assert moved.id == descriptor.id


def test_id_tracks_capability_change(descriptor):
    extra = list(descriptor.affordances) + [Affordance(name="explain", summary="Explain the label")]
    assert make_descriptor(affordances=extra).id != descriptor.id


def test_canonical_json_is_key_ordered():
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_round_trip_through_json_preserves_id(descriptor):
    revived = ParticipantDescriptor.model_validate_json(descriptor.model_dump_json())
    assert revived.id == descriptor.id


def test_declared_id_is_verified_on_load(descriptor):
    payload = descriptor.model_dump(mode="json")
    assert payload["id"] == descriptor.id
    assert ParticipantDescriptor(**payload).id == descriptor.id


def test_tampered_descriptor_is_rejected(descriptor):
    payload = descriptor.model_dump(mode="json")
    payload["affordances"][0]["side_effects"] = "irreversible"
    with pytest.raises(ValidationError, match="does not match content hash"):
        ParticipantDescriptor(**payload)


def test_duplicate_affordance_names_rejected():
    dup = [Affordance(name="go", summary="a"), Affordance(name="go", summary="b")]
    with pytest.raises(ValidationError, match="unique"):
        make_descriptor(affordances=dup)


def test_handle_must_be_namespaced():
    with pytest.raises(ValidationError):
        make_descriptor(handle="sentiment")


def test_lookup_helpers(descriptor):
    assert descriptor.affordance("classify").idempotent
    assert descriptor.binding_for("classify").scheme == "hf"
    with pytest.raises(KeyError):
        descriptor.affordance("nope")


def test_worst_side_effect_is_the_maximum(descriptor):
    mixed = list(descriptor.affordances) + [
        Affordance(name="publish", summary="Post it", side_effects=SideEffect.IRREVERSIBLE)
    ]
    assert make_descriptor(affordances=mixed).worst_side_effect is SideEffect.IRREVERSIBLE


def test_content_id_is_short_and_prefixed(descriptor):
    assert content_id(descriptor) == descriptor.id
    assert len(descriptor.id) == len("mk:") + 32
