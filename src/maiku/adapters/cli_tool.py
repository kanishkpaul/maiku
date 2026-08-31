"""Adapt any command-line program.

The command template is the schema: `cli:wc -l {path}` declares one string argument, and
`{count:integer}` declares a typed one. Asking someone to write a JSON spec for a program
they can already describe in one line is the friction that stops adapters getting written.

Substitution happens per-argv-token after splitting, never through a shell, so an argument
containing a semicolon is an argument and not a second command.
"""

import asyncio
import json
import re
import shlex
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from maiku.adapters.base import Adapter, AdapterError, UnknownAffordance, Unreachable
from maiku.adapters.context import CallContext
from maiku.adapters.registry import register
from maiku.adapters.uri import InvalidURI, ParticipantURI
from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.descriptor.enums import (
    AffordanceKind,
    Determinism,
    Kind,
    LatencyClass,
    Residency,
    SideEffect,
    Transport,
)
from maiku.descriptor.participant import (
    ArtifactPolicy,
    Display,
    ParticipantDescriptor,
    Permissions,
    Provenance,
    RuntimeInfo,
)
from maiku.wire.events import ArtifactWritten, Delta, Event, Finished
from maiku.wire.parts import TextPart

PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(?::([a-z]+))?\}")
JSON_TYPES = {"string", "integer", "number", "boolean", "artifact"}
ARTIFACT = "artifact"
DEFAULT_TIMEOUT = 120.0


class Slot:
    __slots__ = ("name", "type")

    def __init__(self, name: str, type_name: str) -> None:
        self.name = name
        self.type = type_name

    @property
    def produces_file(self) -> bool:
        return self.type == ARTIFACT


def parse_slots(template: str) -> list[Slot]:
    slots = [Slot(name, kind or "string") for name, kind in PLACEHOLDER.findall(template)]
    for slot in slots:
        if slot.type not in JSON_TYPES:
            raise InvalidURI(f"{slot.type!r} is not a placeholder type; use {sorted(JSON_TYPES)}")
    if len({s.name for s in slots}) != len(slots):
        raise InvalidURI(f"duplicate placeholder in {template!r}")
    return slots


def build_schema(slots: list[Slot]) -> dict[str, Any]:
    inputs = [s for s in slots if not s.produces_file]
    return {
        "type": "object",
        "properties": {s.name: {"type": s.type} for s in inputs},
        "required": [s.name for s in inputs],
        "additionalProperties": False,
    }


@register
class CLIAdapter(Adapter):
    scheme = "cli"

    def __init__(self, uri: ParticipantURI) -> None:
        self._uri = uri
        self._template = uri.target
        self._slots = parse_slots(self._template)
        self._program = shlex.split(self._template)[0] if self._template.strip() else ""
        if not self._program:
            raise InvalidURI(f"{uri.raw!r} names no program")

        self._name = uri.param("name") or Path(self._program).name
        self._streams = uri.flag("stream")
        self._json = uri.flag("json")
        self._timeout = float(uri.param("timeout", str(DEFAULT_TIMEOUT)) or DEFAULT_TIMEOUT)
        self._effects = SideEffect(uri.param("effects", SideEffect.WRITE.value))
        self._cwd = uri.param("cwd")

    @classmethod
    async def open(cls, uri: ParticipantURI) -> "CLIAdapter":
        return cls(uri)

    @property
    def _output_slot(self) -> Slot | None:
        return next((s for s in self._slots if s.produces_file), None)

    async def describe(self) -> ParticipantDescriptor:
        affordance = Affordance(
            name=self._uri.param("affordance", "run") or "run",
            summary=self._uri.param("summary") or f"Run {self._name}",
            description=f"Command template: {self._template}",
            kind=AffordanceKind.STREAM if self._streams else AffordanceKind.INVOKE,
            input_schema=build_schema(self._slots),
            output_schema={"type": "string"} if not self._json else {},
            determinism=Determinism.SIDE_EFFECTING,
            latency_class=LatencyClass.SECONDS,
            idempotent=self._uri.flag("idempotent"),
            side_effects=self._effects,
        )
        return ParticipantDescriptor(
            handle=f"cli/{self._name.lower()}",
            kind=Kind.TOOL,
            display=Display(
                name=self._name,
                description=self._uri.param("summary") or f"The {self._name} command",
                tags=["cli", "subprocess"],
            ),
            provenance=Provenance(
                vendor=self._name,
                source_uri=self._uri.raw,
                adapter=self.scheme,
                adapter_version=self.version,
            ),
            runtime=RuntimeInfo(
                residency=Residency.SUBPROCESS, host="localhost", max_concurrency=4
            ),
            affordances=[affordance],
            bindings=[
                Binding(
                    scheme=self.scheme,
                    transport=Transport.SUBPROCESS,
                    uri=self._template,
                    config={"program": self._program},
                )
            ],
            artifacts=ArtifactPolicy(
                can_write=["application/octet-stream"] if self._output_slot else []
            ),
            permissions=Permissions(side_effects=self._effects),
        )

    async def probe(self):
        from shutil import which

        from maiku.wire.health import Health

        found = which(self._program) or (Path(self._program).exists() and self._program)
        return Health.up() if found else Health.down(f"{self._program!r} is not on PATH")

    def _argv(self, arguments: dict[str, Any], output: Path | None) -> list[str]:
        values = {s.name: arguments.get(s.name) for s in self._slots}
        if output is not None and (slot := self._output_slot):
            values[slot.name] = str(output)

        def fill(token: str) -> str:
            return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), token)

        return [fill(token) for token in shlex.split(self._template)]

    async def invoke(
        self, affordance: str, arguments: dict[str, Any], ctx: CallContext
    ) -> AsyncIterator[Event]:
        descriptor = await self.describe()
        if affordance != descriptor.affordances[0].name:
            raise UnknownAffordance(f"{affordance!r} is not {self._name}'s affordance")

        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "output" if self._output_slot else None
            argv = self._argv(arguments, output)

            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self._cwd,
                )
            except OSError as exc:
                raise Unreachable(f"cannot run {argv[0]!r}: {exc}") from exc

            lines: list[str] = []
            if self._streams:
                index = 0
                assert process.stdout
                while raw := await process.stdout.readline():
                    ctx.raise_if_cancelled()
                    line = raw.decode(errors="replace")
                    lines.append(line)
                    yield Delta(part=TextPart(text=line), index=index)
                    index += 1
                stderr = (await process.stderr.read()).decode(errors="replace")
                await process.wait()
                stdout = "".join(lines)
            else:
                try:
                    out, err = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
                except TimeoutError as exc:
                    process.kill()
                    raise Unreachable(f"{self._name} exceeded {self._timeout}s") from exc
                stdout, stderr = out.decode(errors="replace"), err.decode(errors="replace")

            if process.returncode != 0:
                raise AdapterError(
                    f"{self._name} exited {process.returncode}: {stderr.strip()[:500]}",
                    detail={"argv": argv, "returncode": process.returncode},
                )

            if output is not None and output.exists() and ctx.artifacts is not None:
                ref = await ctx.artifacts.write(
                    output,
                    media_type=self._uri.param("media_type", "application/octet-stream"),
                    name=self._uri.param("filename") or "output",
                )
                yield ArtifactWritten(ref=ref)
                yield Finished(result=ref.digest)
                return

        yield Finished(result=_parse(stdout, self._json))


def _parse(stdout: str, as_json: bool) -> Any:
    if not as_json:
        return stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"stdout was not JSON: {exc}") from exc
