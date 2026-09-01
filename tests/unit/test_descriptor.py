import pytest
from pydantic import ValidationError

from maiku.descriptor import (
    Affordance,
    Binding,
    Display,
    ParticipantDescriptor,
    Permissions,
    Provenance,
    Residency,
    RuntimeInfo,
    SideEffect,
    Transport,
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


def served_at(uri: str) -> Binding:
    return Binding(scheme="openai", transport=Transport.HTTP, uri=uri)


def test_id_ignores_the_port_it_is_served_on():
    moved = [
        make_descriptor(bindings=[served_at(f"http://127.0.0.1:{port}/v1/chat/completions")])
        for port in (11434, 11435)
    ]
    assert moved[0].id == moved[1].id


def test_id_ignores_how_many_ways_it_is_reachable(descriptor):
    """Stage 3 unions the bindings of every discoverer that answered for one address."""
    also_over_http = make_descriptor(
        bindings=[*descriptor.bindings, served_at("http://127.0.0.1:11434/v1/chat/completions")]
    )
    assert also_over_http.id == descriptor.id


def test_id_ignores_what_it_is_called(descriptor):
    named = descriptor.display.model_dump()
    for change in ({"name": "Feelings"}, {"icon": "brain"}, {"tags": ["nlp"]}):
        assert make_descriptor(display=Display(**named | change)).id == descriptor.id


def test_id_ignores_who_made_it(descriptor):
    made_by = descriptor.provenance.model_dump()
    for change in ({"vendor": "ollama"}, {"version": "2.0.0"}, {"adapter": "openai_compat"}):
        assert make_descriptor(provenance=Provenance(**made_by | change)).id == descriptor.id


def test_id_tracks_declared_side_effects(descriptor):
    riskier = make_descriptor(permissions=Permissions(side_effects=SideEffect.IRREVERSIBLE))
    assert riskier.id != descriptor.id


def test_id_tracks_a_widened_input_schema(descriptor):
    classify = descriptor.affordance("classify")
    widened = classify.model_copy(
        update={
            "input_schema": classify.input_schema
            | {"properties": {"text": {"type": "string"}, "language": {"type": "string"}}}
        }
    )
    assert make_descriptor(affordances=[widened]).id != descriptor.id


def test_declared_id_survives_an_edit_outside_identity(descriptor):
    payload = descriptor.model_dump(mode="json")
    payload["display"]["name"] = "Feelings"
    payload["bindings"][0]["uri"] = "http://127.0.0.1:11435/v1/chat/completions"
    assert ParticipantDescriptor(**payload).id == descriptor.id


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
