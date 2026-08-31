"""Regenerate schemas/participant-descriptor.schema.json."""

from pathlib import Path

from maiku.descriptor.schema import write_schema

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(write_schema(root / "schemas" / "participant-descriptor.schema.json"))
