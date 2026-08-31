"""JSON Schema emission for the descriptor.

Published so non-Python implementations can validate maiku documents without a Python
runtime — an adapter ecosystem that only works from Python is not an adapter ecosystem.
"""

import json
from pathlib import Path
from typing import Any

from maiku.descriptor.participant import SCHEMA_VERSION, ParticipantDescriptor

SCHEMA_ID = "https://maiku.dev/schemas/participant-descriptor.schema.json"

_ID_PROPERTY: dict[str, Any] = {
    "type": "string",
    "pattern": "^mk:[0-9a-f]{32}$",
    "description": "Content hash of the descriptor. Derived, and verified when present.",
}


def participant_json_schema() -> dict[str, Any]:
    schema = ParticipantDescriptor.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = "maiku ParticipantDescriptor"
    schema["x-maiku-schema-version"] = SCHEMA_VERSION

    # Optional on the wire, required in a dump: `id` is derived, never authored.
    schema["properties"]["id"] = _ID_PROPERTY
    return schema


def write_schema(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(participant_json_schema(), indent=2, sort_keys=True) + "\n")
    return path
