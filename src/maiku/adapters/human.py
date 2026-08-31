"""A person, as a participant.

Not a special case bolted onto the runtime - the same descriptor, the same event stream,
the same grant checks as a GPU. The only thing that marks a human out is
`latency_class: human`, and everything downstream already knows how to read that.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance
from maiku.adapters.channels import Channel, channel_named
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import ParticipantURI
from maiku.descriptor.affordance import Affordance, Example
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Determinism,
    Device,
    Kind,
    LatencyClass,
    Residency,
    SideEffect,
    Transport,
)
from maiku.descriptor.participant import (
    Display,
    ParticipantDescriptor,
    Provenance,
    Resources,
    RuntimeInfo,
)
from maiku.wire.events import Event, Finished, Progress
from maiku.wire.health import Health

ASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "context": {"type": "string", "description": "Background the person may need"},
    },
    "required": ["question"],
}

APPROVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "detail": {"type": "object"},
    },
    "required": ["reason"],
}

CHOOSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}, "minItems": 2},
    },
    "required": ["prompt", "options"],
}


def _affordances() -> list[Affordance]:
    return [
        Affordance(
            name="ask",
            summary="Ask the person a question and wait for their answer",
            kind=AffordanceKind.INVOKE,
            input_schema=ASK_SCHEMA,
            output_schema={"type": "string"},
            determinism=Determinism.STOCHASTIC,
            latency_class=LatencyClass.HUMAN,
            side_effects=SideEffect.NONE,
            examples=[Example(input={"question": "Which of these looks right?"})],
        ),
        Affordance(
            name="approve",
            summary="Ask the person to approve an action",
            kind=AffordanceKind.INVOKE,
            input_schema=APPROVE_SCHEMA,
            output_schema={"type": "boolean"},
            determinism=Determinism.STOCHASTIC,
            latency_class=LatencyClass.HUMAN,
            side_effects=SideEffect.NONE,
        ),
        Affordance(
            name="choose",
            summary="Ask the person to pick one of several options",
            kind=AffordanceKind.INVOKE,
            input_schema=CHOOSE_SCHEMA,
            output_schema={"type": "string"},
            determinism=Determinism.STOCHASTIC,
            latency_class=LatencyClass.HUMAN,
            side_effects=SideEffect.NONE,
        ),
    ]


@register
class HumanAdapter(Adapter):
    scheme = "human"

    def __init__(self, uri: ParticipantURI, channel: Channel) -> None:
        self._uri = uri
        self._channel = channel
        self._name = uri.target or "human"

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "HumanAdapter":
        return cls(uri, channel_named(uri.param("channel", "cli") or "cli"))

    def with_channel(self, channel: Channel) -> "HumanAdapter":
        return HumanAdapter(self._uri, channel)

    async def describe(self) -> ParticipantDescriptor:
        return ParticipantDescriptor(
            handle=f"human/{self._name}",
            kind=Kind.HUMAN,
            display=Display(
                name=self._name,
                description=f"A person, reachable over {self._channel.name}",
                icon="🧑",
                tags=["human", "approval", self._channel.name],
            ),
            provenance=Provenance(adapter=self.scheme, adapter_version=self.version),
            runtime=RuntimeInfo(
                residency=Residency.HUMAN,
                device=Device.NONE,
                resources=Resources(),
                max_concurrency=1,
            ),
            affordances=_affordances(),
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.TTY,
                    uri=self._uri.raw,
                    config={"channel": self._channel.name},
                )
            ],
        )

    async def probe(self) -> Health:
        # A person is "online" in the sense that the doorbell is wired up. Whether they
        # answer is what the call timeout is for.
        return Health.up()

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        started = time.time()
        yield Progress(message=f"waiting for {self._name}")

        if affordance == "ask":
            question = arguments["question"]
            if context := arguments.get("context"):
                question = f"{question}\n\n{context}"
            result: Any = await self._channel.ask(question, {"type": "string"})
        elif affordance == "approve":
            result = await self._channel.approve(arguments["reason"], arguments.get("detail") or {})
        elif affordance == "choose":
            options = arguments["options"]
            listing = "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(options))
            raw = await self._channel.ask(f"{arguments['prompt']}\n{listing}", {"type": "string"})
            result = _pick(str(raw), options)
        else:
            raise UnknownAffordance(f"{affordance!r} is not something a person exposes")

        yield Progress(message=f"answered in {time.time() - started:.1f}s", fraction=1.0)
        yield Finished(result=result)


def _pick(answer: str, options: list[str]) -> str:
    """Accept either the option text or its number, because people type both."""
    answer = answer.strip()
    if answer in options:
        return answer
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return options[int(answer) - 1]
    raise AdapterError(f"{answer!r} is not one of {options}")
