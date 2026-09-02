"""Descriptor to and from an A2A AgentCard.

Outbound is near-lossless. Inbound is not, and honestly cannot be: A2A skills carry no
JSON Schema, so an ingested agent gets the standard message-shaped input schema rather
than a fabricated one. Guessing types we were never told is how a registry starts lying.
"""

import json
from typing import TYPE_CHECKING, Any

from maiku.descriptor.affordance import Affordance, Example
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Kind,
    LatencyClass,
    Residency,
    SideEffect,
    Transport,
)
from maiku.descriptor.participant import (
    Display,
    IODefaults,
    ParticipantDescriptor,
    Provenance,
    RuntimeInfo,
)
from maiku.projections.naming import handle_slug
from maiku.projections.visible import visible

if TYPE_CHECKING:
    from maiku.runtime.grants import Grant

PROTOCOL_VERSION = "0.3.0"

_TRANSPORT_OUT: dict[Transport, str] = {
    Transport.JSONRPC: "JSONRPC",
    Transport.GRPC: "GRPC",
    Transport.HTTP: "HTTP+JSON",
    Transport.SSE: "HTTP+JSON",
}
_TRANSPORT_IN: dict[str, Transport] = {
    "JSONRPC": Transport.JSONRPC,
    "GRPC": Transport.GRPC,
    "HTTP+JSON": Transport.HTTP,
}

MESSAGE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "Text of the message to send"},
        "parts": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["message"],
}


def _skill(affordance: Affordance, descriptor: ParticipantDescriptor) -> dict[str, Any]:
    return {
        "id": affordance.name,
        "name": affordance.summary or affordance.name,
        "description": affordance.description or affordance.summary,
        "tags": affordance.tags or descriptor.display.tags,
        "examples": [e.note or json.dumps(e.input, default=str) for e in affordance.examples],
        "inputModes": descriptor.io_defaults.input_modes,
        "outputModes": descriptor.io_defaults.output_modes,
    }


def to_agent_card(
    descriptor: ParticipantDescriptor, grant: "Grant", base_url: str | None = None
) -> dict[str, Any]:
    binding = descriptor.bindings[0]
    url = base_url or binding.uri or f"urn:maiku:{descriptor.handle}"
    skills = visible(descriptor, grant)

    return {
        "protocolVersion": PROTOCOL_VERSION,
        "name": descriptor.display.name,
        "description": descriptor.display.description,
        "url": url,
        "preferredTransport": _TRANSPORT_OUT.get(binding.transport, "JSONRPC"),
        "version": descriptor.provenance.version or "0.0.0",
        "provider": {
            "organization": descriptor.provenance.vendor or "unknown",
            "url": descriptor.provenance.source_uri or url,
        },
        "capabilities": {
            "streaming": any(a.streaming for a in skills),
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": descriptor.io_defaults.input_modes,
        "defaultOutputModes": descriptor.io_defaults.output_modes,
        "skills": [_skill(a, descriptor) for a in skills],
        "supportsAuthenticatedExtendedCard": False,
        "_meta": {"maiku/handle": descriptor.handle, "maiku/id": descriptor.id},
    }


def from_agent_card(card: dict[str, Any], handle: str | None = None) -> ParticipantDescriptor:
    name = card.get("name") or "agent"
    streaming = bool(card.get("capabilities", {}).get("streaming"))
    kind = AffordanceKind.STREAM if streaming else AffordanceKind.INVOKE

    skills = card.get("skills") or [{"id": "message", "name": "Send a message"}]
    affordances = [
        Affordance(
            name=str(skill.get("id", f"skill_{i}")).lower().replace("-", "_"),
            summary=(skill.get("name") or skill.get("id") or "")[:200],
            description=skill.get("description") or "",
            kind=kind,
            input_schema=dict(MESSAGE_INPUT_SCHEMA),
            tags=skill.get("tags") or [],
            examples=[Example(note=str(e)) for e in skill.get("examples") or []],
            latency_class=LatencyClass.MINUTES,
            side_effects=SideEffect.EXTERNAL,
        )
        for i, skill in enumerate(skills)
    ]

    transport = _TRANSPORT_IN.get(card.get("preferredTransport", ""), Transport.JSONRPC)
    provider = card.get("provider") or {}

    return ParticipantDescriptor(
        handle=handle or f"a2a/{handle_slug(name).lower()}",
        kind=Kind.AGENT,
        display=Display(name=name, description=card.get("description") or ""),
        provenance=Provenance(
            vendor=provider.get("organization", ""),
            version=card.get("version", ""),
            source_uri=card.get("url"),
            adapter="a2a",
        ),
        runtime=RuntimeInfo(residency=Residency.REMOTE, host=card.get("url")),
        affordances=affordances,
        bindings=[Binding(scheme="a2a", transport=transport, uri=card.get("url"))],
        io_defaults=IODefaults(
            input_modes=card.get("defaultInputModes") or ["text/plain"],
            output_modes=card.get("defaultOutputModes") or ["text/plain"],
        ),
    )
