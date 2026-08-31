"""Descriptor to OpenAI-style function tools."""

from typing import Any

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.projections.naming import flatten

MAX_DESCRIPTION = 1024


def to_tool(descriptor: ParticipantDescriptor, affordance: Affordance) -> dict[str, Any]:
    description = (affordance.description or affordance.summary)[:MAX_DESCRIPTION]
    return {
        "type": "function",
        "function": {
            "name": flatten(descriptor.handle, affordance.name),
            "description": description,
            "parameters": affordance.input_schema,
        },
    }


def to_tools(descriptor: ParticipantDescriptor) -> list[dict[str, Any]]:
    return [to_tool(descriptor, a) for a in descriptor.affordances]
