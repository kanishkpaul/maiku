"""Schema fragments for values that JSON Schema alone cannot describe.

An artifact-valued argument is a string on the wire and a file in practice. The vocabulary
extension says so out loud, so a caller can resolve it and a validator still sees plain
JSON.
"""

from typing import Any

ARTIFACT_KEY = "x-maiku-artifact"
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"


def artifact_schema(media_type: str = "*/*", description: str = "") -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": DIGEST_PATTERN,
        "description": description or f"Artifact digest ({media_type})",
        ARTIFACT_KEY: {"media_type": media_type},
    }


def is_artifact_schema(schema: dict[str, Any]) -> bool:
    return ARTIFACT_KEY in schema


def artifact_arguments(input_schema: dict[str, Any]) -> list[str]:
    """Names of top-level arguments that carry artifact digests."""
    properties = input_schema.get("properties") or {}
    return [
        name
        for name, sub in properties.items()
        if isinstance(sub, dict) and is_artifact_schema(sub)
    ]
