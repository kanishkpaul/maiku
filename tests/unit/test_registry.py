import sqlite3

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


def test_by_capability_id_finds_every_handle_affording_the_same_thing(registry):
    alice = make_descriptor(handle="human/alice")
    bob = make_descriptor(handle="human/bob")
    registry.add(alice, "human:alice")
    registry.add(bob, "human:bob")

    assert alice.capability_id == bob.capability_id
    found = registry.by_capability_id(alice.capability_id)
    assert [e.handle for e in found] == ["human/alice", "human/bob"]
    assert registry.by_content_id(alice.id) == found[:1]


REGISTRY_BEFORE_CAPABILITY_IDS = """
CREATE TABLE participants (
    handle TEXT PRIMARY KEY, content_id TEXT NOT NULL, uri TEXT NOT NULL,
    kind TEXT NOT NULL, descriptor TEXT NOT NULL, health TEXT,
    first_seen REAL NOT NULL, last_seen REAL NOT NULL
);
"""


def test_an_existing_registry_is_backfilled_not_left_blank(tmp_path, descriptor):
    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript(REGISTRY_BEFORE_CAPABILITY_IDS)
    old.execute(
        "INSERT INTO participants VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
        (descriptor.handle, descriptor.id, "u", descriptor.kind.value,
         descriptor.model_dump_json(), 1.0, 1.0),
    )
    old.commit()
    old.close()

    with Registry(path) as registry:
        found = registry.by_capability_id(descriptor.capability_id)
        assert [e.handle for e in found] == [descriptor.handle]


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


def test_pre_change_descriptor_is_re_derived_on_read(tmp_path, descriptor):
    import json

    from maiku.descriptor.participant import ParticipantDescriptor

    path = tmp_path / "registry.sqlite"
    row = descriptor.model_dump(mode="json")
    row["id"] = "mk:" + "a" * 32

    with Registry(path) as r:
        r.add(descriptor, "u")
        r._db.execute(
            "UPDATE participants SET descriptor = ? WHERE handle = ?",
            (json.dumps(row), descriptor.handle),
        )
        r._db.commit()

    with Registry(path) as r:
        entries = r.list()
        assert len(entries) == 1
        assert entries[0].handle == descriptor.handle
        assert entries[0].descriptor.id == descriptor.id

    # Verify wire descriptors with tampered id are still rejected
    row_tampered = json.dumps(row)
    with pytest.raises(ValueError, match="does not match content hash"):
        ParticipantDescriptor.model_validate_json(row_tampered)


def test_unreadable_row_does_not_break_listing(tmp_path, descriptor):
    path = tmp_path / "registry.sqlite"
    good = descriptor
    with Registry(path) as r:
        r.add(good, "u1")
        bad_insert = (
            "INSERT INTO participants VALUES "
            "('local/bad', 'id', 'cap', 'u2', 'agent', 'invalid json {{{', NULL, 0, 0)"
        )
        r._db.execute(bad_insert)
        r._db.commit()

    with Registry(path) as r:
        entries = r.list()
        assert [e.handle for e in entries] == [good.handle]
        assert "local/bad" in r.unreadable

        found = r.find("sentiment")
        assert [e.handle for e in found] == [good.handle]


def test_migration_fault_tolerant_and_re_runnable(tmp_path, descriptor):
    import json
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE participants (
            handle TEXT PRIMARY KEY, content_id TEXT NOT NULL, uri TEXT NOT NULL,
            kind TEXT NOT NULL, descriptor TEXT NOT NULL, health TEXT,
            first_seen REAL NOT NULL, last_seen REAL NOT NULL
        )"""
    )
    good_row = descriptor.model_dump(mode="json")
    stale_row = descriptor.model_dump(mode="json")
    stale_row["id"] = "mk:" + "a" * 32

    conn.execute(
        "INSERT INTO participants VALUES (?, ?, ?, ?, ?, NULL, 0, 0)",
        ("local/good", descriptor.id, "u1", descriptor.kind.value, json.dumps(good_row)),
    )
    conn.execute(
        "INSERT INTO participants VALUES (?, ?, ?, ?, ?, NULL, 0, 0)",
        ("local/stale", "mk:" + "a" * 32, "u2", descriptor.kind.value, json.dumps(stale_row)),
    )
    conn.commit()
    conn.close()

    with Registry(path) as r:
        assert len(r.list()) == 2
        assert r.by_capability_id(descriptor.capability_id) != []

    with Registry(path) as r:
        assert len(r.list()) == 2


def test_init_failure_does_not_leak_connection(tmp_path, monkeypatch):
    path = tmp_path / "fail.sqlite"

    def bad_migrate(self):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(Registry, "_migrate", bad_migrate)
    with pytest.raises(RuntimeError):
        Registry(path)

    # Should be able to open/connect sqlite file without "database is locked"
    conn = sqlite3.connect(path)
    conn.close()

