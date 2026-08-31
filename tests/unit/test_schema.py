import json
from pathlib import Path

import jsonschema
import pytest

from maiku.descriptor.schema import participant_json_schema

CHECKED_IN = Path(__file__).resolve().parents[2] / "schemas" / "participant-descriptor.schema.json"


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schema = participant_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_checked_in_schema_is_current():
    on_disk = json.loads(CHECKED_IN.read_text())
    assert on_disk == participant_json_schema(), "run scripts/emit_schema.py"


def test_a_dumped_descriptor_validates(validator, descriptor):
    validator.validate(descriptor.model_dump(mode="json"))


def test_schema_rejects_unknown_top_level_key(validator, descriptor):
    payload = descriptor.model_dump(mode="json") | {"nonsense": 1}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)
