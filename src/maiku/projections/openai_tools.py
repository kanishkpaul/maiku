"""Descriptor to OpenAI-style function tools."""

from typing import TYPE_CHECKING, Any

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.projections.naming import flatten
from maiku.projections.visible import visible

if TYPE_CHECKING:
    from maiku.runtime.grants import Grant

MAX_DESCRIPTION = 1024


def _tool(descriptor: ParticipantDescriptor, affordance: Affordance) -> dict[str, Any]:
    description = (affordance.description or affordance.summary)[:MAX_DESCRIPTION]
    return {
        "type": "function",
        "function": {
            "name": flatten(descriptor.handle, affordance.name),
            "description": description,
            "parameters": affordance.input_schema,
        },
    }


def to_tools(descriptor: ParticipantDescriptor, grant: "Grant") -> list[dict[str, Any]]:
    return [_tool(descriptor, a) for a in visible(descriptor, grant)]
