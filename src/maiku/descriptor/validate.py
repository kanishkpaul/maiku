"""Checking values against an affordance's declared schemas.

Pure functions returning problems rather than raising, so both the adapter boundary and the
router can use them and choose their own consequences.
"""

from functools import lru_cache
from typing import Any

from maiku.descriptor.affordance import Affordance


@lru_cache(maxsize=1)
def _validator_class() -> Any:
    from jsonschema import Draft202012Validator

    return Draft202012Validator


def errors_for(schema: dict[str, Any], value: Any) -> list[str]:
    if not schema:
        return []
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in _validator_class()(schema).iter_errors(value)
    ]


def argument_errors(affordance: Affordance, arguments: dict[str, Any]) -> list[str]:
    return errors_for(affordance.input_schema, arguments)


def result_errors(affordance: Affordance, result: Any) -> list[str]:
    return errors_for(affordance.output_schema, result)
