"""Argument and result checking against declared schemas.

Inputs are rejected: calling a participant with arguments it never claimed to accept is a
caller bug, and failing at the boundary beats failing inside someone else's model.

Outputs are only reported. A participant whose result drifts from its declared schema is
worth knowing about, but discarding a real answer over a schema quibble helps nobody.
"""

from functools import lru_cache
from typing import Any

from maiku.adapters.base import InvalidArguments
from maiku.descriptor.affordance import Affordance


@lru_cache(maxsize=1)
def _validator_class() -> Any:
    from jsonschema import Draft202012Validator

    return Draft202012Validator


def errors_for(schema: dict[str, Any], value: Any) -> list[str]:
    if not schema:
        return []
    validator = _validator_class()(schema)
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(value)
    ]


def check_arguments(affordance: Affordance, arguments: dict[str, Any]) -> None:
    problems = errors_for(affordance.input_schema, arguments)
    if problems:
        raise InvalidArguments(
            f"arguments for {affordance.name!r} are invalid",
            detail={"errors": problems},
        )


def result_warnings(affordance: Affordance, result: Any) -> list[str]:
    return errors_for(affordance.output_schema, result)
