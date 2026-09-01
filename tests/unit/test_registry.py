import pytest

from maiku.descriptor import Affordance, Binding, Transport
from maiku.descriptor.enums import Kind
from maiku.runtime.registry import Registry, UnknownParticipant, searchable_text
from maiku.wire.health import Health
from tests.conftest import make_descriptor


@pytest.fixture
def registry(tmp_path):
    with Registry(tmp_path / "registry.sqlite") as r:
        yield r


def test_add_and_get(registry, descriptor):
    registry.add(descriptor, "hf:sentiment")
    entry = registry.get(descriptor.handle)
    assert entry.descriptor.id == descriptor.id
    assert entry.uri == "hf:sentiment"


def test_missing_handle_raises(registry):
    with pytest.raises(UnknownParticipant):
        registry.get("nobody/here")


def test_a_first_add_is_new(registry, descriptor):
    registered = registry.add(descriptor, "hf:sentiment")
    assert registered.is_new
    assert registered.identity_changed is False


def test_re_adding_keeps_first_seen_and_reports_nothing_changed(registry, descriptor):
    first = registry.add(descriptor, "hf:sentiment")
    again = registry.add(descriptor, "hf:sentiment-v2")
    assert again.entry.first_seen == first.entry.first_seen
    assert again.is_new is False
    assert again.identity_changed is False
    assert registry.get(descriptor.handle).uri == "hf:sentiment-v2"


def test_moving_the_endpoint_is_not_an_identity_change(registry, descriptor):
    registry.add(descriptor, "openai:local")
    moved = make_descriptor(
        bindings=[
            Binding(scheme="openai", transport=Transport.HTTP, uri="http://127.0.0.1:11435/v1")
        ]
    )
    assert registry.add(moved, "openai:local").identity_changed is False


def test_a_new_affordance_under_a_known_handle_is_reported(registry, descriptor):
    registry.add(descriptor, "u")
    grown = make_descriptor(
        affordances=[*descriptor.affordances, Affordance(name="explain", summary="Explain it")]
    )
    registered = registry.add(grown, "u")
    assert registered.identity_changed
    assert registered.replaced_content_id == descriptor.id


def test_by_content_id_finds_the_stored_capability_set(registry, descriptor):
    registry.add(descriptor, "u")
    assert [e.handle for e in registry.by_content_id(descriptor.id)] == [descriptor.handle]
    assert registry.by_content_id("mk:" + "0" * 32) == []


def test_an_update_rebuilds_the_search_index_rather_than_duplicating_it(registry, descriptor):
    registry.add(descriptor, "u")
    registry.add(descriptor, "u")
    assert [e.handle for e in registry.find("sentiment")] == [descriptor.handle]


def test_remove(registry, descriptor):
    registry.add(descriptor, "u")
    assert registry.remove(descriptor.handle) is True
    assert registry.remove(descriptor.handle) is False


def test_list_filters_by_kind(registry, descriptor):
    registry.add(descriptor, "u")
    registry.add(make_descriptor(handle="local/agent", kind=Kind.AGENT), "u")
    assert len(registry.list()) == 2
    assert [e.handle for e in registry.list(kind=Kind.AGENT)] == ["local/agent"]


def test_health_is_recorded_and_filters_listing(registry, descriptor):
    registry.add(descriptor, "u")
    registry.add(make_descriptor(handle="local/offline"), "u")
    registry.record_health(descriptor.handle, Health.up(3.0))
    registry.record_health("local/offline", Health.down("connection refused"))

    assert [e.handle for e in registry.list(online=True)] == [descriptor.handle]
    assert [e.handle for e in registry.list(online=False)] == ["local/offline"]
    assert registry.get("local/offline").health.detail == "connection refused"


def test_search_matches_prose_not_just_names(registry, descriptor):
    registry.add(descriptor, "u")
    assert [e.handle for e in registry.find("sentiment")] == [descriptor.handle]
    assert [e.handle for e in registry.find("positive negative")] == [descriptor.handle]
    assert registry.find("nothing matches this") == []


@pytest.mark.parametrize("query", ['" OR "', "classify AND NOT", "*", '"'])
def test_user_text_is_never_read_as_fts_syntax(registry, descriptor, query):
    registry.add(descriptor, "u")
    registry.find(query)  # must not raise


def test_searchable_text_includes_affordance_prose(descriptor):
    text = searchable_text(descriptor)
    assert "Label a sentence positive or negative" in text
    assert "classify" in text
