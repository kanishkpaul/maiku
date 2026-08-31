"""Canonical serialization and content addressing.

Identity is what a participant *is and can do* — not where it happens to be running or
whether it is up right now. So residency, liveness and the signature itself are excluded
from the hash: restarting Ollama on another port must not mint a new participant.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maiku.descriptor.participant import ParticipantDescriptor

VOLATILE_FIELDS = frozenset({"id", "signature", "liveness", "runtime"})

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
