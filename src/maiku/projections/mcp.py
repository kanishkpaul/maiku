"""Descriptor to MCP tools.

The behavioural hints translate exactly, which is the point: a participant that declared
`side_effects: irreversible` should make an MCP client hesitate without anyone restating
that fact by hand.
"""

from typing import Any

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.enums import SideEffect
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.projections.naming import flatten

READ_ONLY = frozenset({SideEffect.NONE, SideEffect.READ})


def annotations(affordance: Affordance) -> dict[str, Any]:
    effect = affordance.side_effects
    return {
        "title": affordance.summary,
        "readOnlyHint": effect in READ_ONLY,
        "destructiveHint": effect is SideEffect.IRREVERSIBLE,
        "idempotentHint": affordance.idempotent,
        "openWorldHint": effect in {SideEffect.EXTERNAL, SideEffect.IRREVERSIBLE},
    }


def to_tool(descriptor: ParticipantDescriptor, affordance: Affordance) -> dict[str, Any]:
    description = affordance.description or affordance.summary
    if descriptor.display.description:
        description = f"{description}\n\nProvided by {descriptor.display.name}."

    tool: dict[str, Any] = {
        "name": flatten(descriptor.handle, affordance.name),
        "title": f"{descriptor.display.name}: {affordance.summary}",
        "description": description,
        "inputSchema": affordance.input_schema,
        "annotations": annotations(affordance),
        "_meta": {
            "maiku/participant": descriptor.handle,
            "maiku/affordance": affordance.name,
            "maiku/id": descriptor.id,
            "maiku/latency": affordance.latency_class.value,
        },
    }
    if affordance.output_schema:
        tool["outputSchema"] = affordance.output_schema
    return tool


def to_tools(descriptor: ParticipantDescriptor) -> list[dict[str, Any]]:
    return [to_tool(descriptor, a) for a in descriptor.affordances]
