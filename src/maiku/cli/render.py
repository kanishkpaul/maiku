"""Terminal output.

Rich when it is installed, plain text when it is not - the CLI should never be the reason
a participant cannot be inspected on a bare machine.
"""

import json
from typing import Any

from maiku.descriptor.participant import ParticipantDescriptor
from maiku.runtime.registry import Entry
from maiku.wire.events import (
    ArtifactWritten,
    Delta,
    Event,
    Failed,
    Finished,
    Log,
    NeedsApproval,
    NeedsInput,
    Progress,
    Usage,
)
from maiku.wire.parts import TextPart

STATUS = {True: "up", False: "down", None: "?"}


def status_of(entry: Entry) -> str:
    return STATUS[entry.health.online if entry.health else None]


def listing(entries: list[Entry]) -> str:
    if not entries:
        return "no participants yet - try: maiku add python:my.module"

    rows = [
        (
            entry.handle,
            entry.descriptor.kind.value,
            status_of(entry),
            str(len(entry.descriptor.affordances)),
            entry.descriptor.runtime.residency.value,
            entry.uri,
        )
        for entry in entries
    ]
    headers = ("HANDLE", "KIND", "STATUS", "ACTS", "WHERE", "URI")
    return _table(headers, rows)


def detail(descriptor: ParticipantDescriptor) -> str:
    lines = [
        f"{descriptor.handle}  ({descriptor.kind.value})",
        f"  {descriptor.display.description or descriptor.display.name}",
        f"  id         {descriptor.id}",
        f"  runs       {descriptor.runtime.residency.value} on {descriptor.runtime.device.value}",
        f"  effects    {descriptor.worst_side_effect.value}"
        f"  approval={descriptor.permissions.approval.value}",
        "",
        "  affordances",
    ]
    for affordance in descriptor.affordances:
        flags = [affordance.kind.value, affordance.latency_class.value]
        if affordance.idempotent:
            flags.append("idempotent")
        if affordance.scopes:
            flags.append("scopes=" + ",".join(affordance.scopes))
        lines.append(f"    {affordance.name:<20} {affordance.summary}")
        lines.append(f"    {'':<20} [{' '.join(flags)}] effects={affordance.side_effects.value}")
        required = affordance.input_schema.get("required") or []
        properties = list(affordance.input_schema.get("properties") or {})
        if properties:
            shown = ", ".join(f"{p}{'*' if p in required else ''}" for p in properties)
            lines.append(f"    {'':<20} in: {shown}")

    # One participant may be reachable several ways; discovery makes that ordinary.
    lines += ["", "  bindings"]
    for binding in descriptor.bindings:
        serves = ", ".join(binding.affordances) or "all"
        lines.append(f"    {binding.scheme:<20} {binding.uri or binding.transport.value}")
        lines.append(f"    {'':<20} serves: {serves}")
    return "\n".join(lines)


def event_line(event: Event) -> str | None:
    """One line per event, or None for events that only matter in aggregate."""
    if isinstance(event, Delta):
        return None
    if isinstance(event, Progress):
        return f"... {event.message}" if event.message else None
    if isinstance(event, Log):
        return f"[{event.level}] {event.message}"
    if isinstance(event, ArtifactWritten):
        return f"[artifact] {event.ref.digest} ({event.ref.media_type})"
    if isinstance(event, NeedsApproval):
        return f"[approval] {event.reason}"
    if isinstance(event, NeedsInput):
        return f"[input] {event.prompt}"
    if isinstance(event, Usage):
        return f"[usage] {event.amount:g} {event.unit}"
    if isinstance(event, Failed):
        return f"[failed] {event.code}: {event.message}"
    return None


def delta_text(event: Event) -> str:
    return event.part.text if isinstance(event, Delta) and isinstance(event.part, TextPart) else ""


def result_text(event: Finished) -> str:
    if isinstance(event.result, str):
        return event.result
    return json.dumps(event.result, indent=2, default=str)


def as_json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str, sort_keys=True)


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    body = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)) for row in rows]
    return "\n".join([line, *body])
