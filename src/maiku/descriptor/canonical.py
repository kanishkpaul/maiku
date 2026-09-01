"""Canonical serialization and content addressing.

Identity is capability: the affordance set, plus the handle that addresses it. Everything
about where a participant runs, how it is reached, who made it and what it is called sits
outside the hash — so restarting Ollama on another port, renaming it, or attributing it to
a vendor all leave the same participant, while adding an affordance mints a new one.

The handle stays inside because it is a position rather than a label: two people who both
afford only `approve` are genuinely different participants.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maiku.descriptor.participant import ParticipantDescriptor

VOLATILE_FIELDS = frozenset(
    {
        "id",
        "signature",
        "liveness",
        "runtime",
        "bindings",  # where and how to reach it, not what it is
        "display",  # a name is not a capability
        "provenance",  # who made it is not what it can do
    }
)

ID_PREFIX = "mk:"
ID_LENGTH = 32


def canonical_json(value: Any) -> bytes:
    """Deterministic JSON: sorted keys, no insignificant whitespace, UTF-8, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def identity_view(descriptor: "ParticipantDescriptor") -> dict[str, Any]:
    return descriptor.model_dump(mode="json", exclude=set(VOLATILE_FIELDS))


def content_hash(descriptor: "ParticipantDescriptor") -> str:
    return hashlib.sha256(canonical_json(identity_view(descriptor))).hexdigest()


def content_id(descriptor: "ParticipantDescriptor") -> str:
    return ID_PREFIX + content_hash(descriptor)[:ID_LENGTH]


def signing_payload(descriptor: "ParticipantDescriptor") -> bytes:
    """Bytes a signature covers.

    Wider than the identity view: a signer is attesting to the endpoint and probe too,
    not merely to the capability list.
    """
    return canonical_json(descriptor.model_dump(mode="json", exclude={"id", "signature"}))
