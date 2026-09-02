"""The maiku command line."""

import asyncio
import json
import sys
from contextlib import aclosing
from pathlib import Path
from typing import Annotated, Any

import typer

from maiku.adapters.base import AdapterError
from maiku.adapters.registry import known_schemes
from maiku.adapters.uri import InvalidURI
from maiku.cli import render
from maiku.cli.args import collect
from maiku.descriptor.enums import Kind, SideEffect
from maiku.discovery.assemble import NothingReadable
from maiku.discovery.base import InvalidAddress
from maiku.gateways.a2a_server import WELL_KNOWN, A2AGateway
from maiku.gateways.http_server import run as run_http
from maiku.gateways.mcp_server import MCPGateway
from maiku.projections import a2a, mcp, openai_tools
from maiku.projections.visible import visible
from maiku.runtime.escalation import route_to
from maiku.runtime.grants import WILDCARD, Capability, Grant, root_grant
from maiku.runtime.registry import UnknownParticipant
from maiku.runtime.workspace import Workspace
from maiku.wire.events import Delta, Failed, Finished

app = typer.Typer(
    name="maiku",
    help="Adapt anything that computes, then let it work with everything else.",
    no_args_is_help=True,
    add_completion=False,
)

GrantOption = Annotated[
    list[str] | None,
    typer.Option(
        "--grant",
        help="A capability the caller holds, e.g. 'ns/name#affordance'. Repeatable. "
        "Omit to describe as the local operator, who holds everything.",
    ),
]

HomeOption = Annotated[
    Path | None, typer.Option("--home", help="Workspace directory (default: ~/.maiku)")
]


def workspace(home: Path | None = None) -> Workspace:
    return Workspace(home)


def grant_from(specs: list[str] | None) -> Grant:
    """What a description is relative to.

    A local operator holds everything, so the default shows the whole participant.
    `--grant` answers the question Rule 2 makes askable: what would a caller holding only
    these capabilities be able to see at all?
    """
    if not specs:
        return root_grant("operator")
    return Grant(
        issuer="operator",
        subject="caller",
        capabilities=[Capability.parse(spec) for spec in specs],
        scopes={WILDCARD},
        max_side_effect=SideEffect.IRREVERSIBLE,
    )


def fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@app.command()
def add(
    uri: Annotated[str, typer.Argument(help="e.g. python:pkg.mod:fn, ollama:qwen3:8b")],
    handle: Annotated[str | None, typer.Option("--as", help="Override the handle")] = None,
    home: HomeOption = None,
) -> None:
    """Adapt something and remember it."""

    async def run() -> None:
        with workspace(home) as ws:
            registered = await ws.add(uri, handle)
            entry = registered.entry
            typer.echo(f"{entry.handle}  ({len(entry.descriptor.affordances)} affordances)")
            if registered.identity_changed:
                typer.secho(
                    f"capabilities changed under this handle "
                    f"(was {registered.replaced_content_id})",
                    fg=typer.colors.YELLOW,
                )
            typer.echo(render.detail(entry.descriptor))

    _run(run())


@app.command(name="ls")
def list_participants(
    kind: Annotated[Kind | None, typer.Option("--kind")] = None,
    online: Annotated[bool | None, typer.Option("--online/--offline")] = None,
    home: HomeOption = None,
) -> None:
    """List everything adapted so far."""
    with workspace(home) as ws:
        entries = ws.registry.list(kind=kind, online=online)
        typer.echo(render.listing(entries))
        if ws.registry.unreadable:
            for handle, reason in sorted(ws.registry.unreadable.items()):
                msg = f"warning: could not read {handle}: {reason}"
                typer.secho(msg, fg=typer.colors.YELLOW, err=True)


@app.command()
def describe(
    handle: str,
    fmt: Annotated[str, typer.Option("--as", help="maiku | json | mcp | a2a | openai")] = "maiku",
    grant_spec: GrantOption = None,
    home: HomeOption = None,
) -> None:
    """Show a participant, optionally projected into another ecosystem's format."""
    with workspace(home) as ws:
        descriptor = _lookup(ws, handle).descriptor
    grant = grant_from(grant_spec)

    if grant_spec:
        parsed_caps = [Capability.parse(s) for s in grant_spec]
        if not any(c.participant in (WILDCARD, handle) for c in parsed_caps):
            msg = f"note: --grant spec does not mention participant {handle!r}"
            typer.secho(msg, fg=typer.colors.YELLOW, err=True)

    vis = visible(descriptor, grant)

    def _json_view() -> str:
        d = descriptor.model_dump(mode="json")
        d["affordances"] = [a.model_dump(mode="json") for a in vis]
        return render.as_json(d)

    views: dict[str, Any] = {
        "maiku": lambda: render.detail(descriptor, affordances=vis),
        "json": _json_view,
        "mcp": lambda: render.as_json(mcp.to_tools(descriptor, grant)),
        "a2a": lambda: render.as_json(a2a.to_agent_card(descriptor, grant)),
        "openai": lambda: render.as_json(openai_tools.to_tools(descriptor, grant)),
    }
    if fmt not in views:
        fail(f"unknown format {fmt!r}; try: {', '.join(views)}")
    typer.echo(views[fmt]())


@app.command()
def find(query: str, home: HomeOption = None) -> None:
    """Search participants by what they say they can do."""
    with workspace(home) as ws:
        typer.echo(render.listing(ws.registry.find(query)))


@app.command()
def rm(handle: str, home: HomeOption = None) -> None:
    """Forget a participant."""
    with workspace(home) as ws:
        if not ws.registry.remove(handle):
            fail(f"no participant {handle!r}")
        typer.echo(f"removed {handle}")


@app.command()
def probe(handle: Annotated[str | None, typer.Argument()] = None, home: HomeOption = None) -> None:
    """Check whether participants are reachable."""

    async def run() -> None:
        with workspace(home) as ws:
            handles = [handle] if handle else ws.registry.handles()
            for target in handles:
                health = await ws.refresh(target)
                mark = "up  " if health.online else "down"
                typer.echo(f"{mark}  {target}  {health.detail}".rstrip())

    _run(run())


@app.command()
def call(
    handle: str,
    affordance: str,
    arg: Annotated[list[str] | None, typer.Option("--arg", "-a", help="key=value")] = None,
    payload: Annotated[str | None, typer.Option("--json", help="Arguments as JSON")] = None,
    human: Annotated[
        str | None, typer.Option("--human", help="Participant to route approvals to")
    ] = None,
    home: HomeOption = None,
) -> None:
    """Call a participant and stream the result."""

    async def run() -> None:
        try:
            arguments = collect(arg or [], payload)
        except ValueError as exc:
            fail(str(exc))
            return

        with workspace(home) as ws:
            _lookup(ws, handle)
            async with ws.session() as session:
                if human:
                    session.responder = route_to(session, human)
                await _stream(session, handle, affordance, arguments)

    _run(run())


@app.command()
def serve(
    protocol: Annotated[str, typer.Argument(help="mcp | a2a")] = "mcp",
    human: Annotated[str | None, typer.Option("--human")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8080,
    grant_spec: GrantOption = None,
    home: HomeOption = None,
) -> None:
    """Serve every adapted participant to an external client."""
    if protocol not in {"mcp", "a2a"}:
        fail(f"unknown protocol {protocol!r}; try: mcp, a2a")

    if host not in {"127.0.0.1", "localhost", "::1"} and not grant_spec:
        fail(
            "refusing to serve root grant on non-loopback host without explicit --grant; "
            "bind 127.0.0.1 or pass --grant"
        )

    grant = grant_from(grant_spec)

    async def run() -> None:
        with workspace(home) as ws:
            async with ws.session() as session:
                if human:
                    session.responder = route_to(session, human)
                if protocol == "mcp":
                    await MCPGateway(session, grant=grant).serve_stdio()
                    return

                gateway = A2AGateway(session, base_url=f"http://{host}:{port}", grant=grant)
                typer.echo(f"a2a on http://{host}:{port}{WELL_KNOWN}", err=True)
                await run_http(_a2a_routes(gateway), host, port)

    _run(run())


def _a2a_routes(gateway: Any) -> Any:
    """Map the three routes A2A needs onto the gateway."""

    async def route(method: str, path: str, body: bytes) -> tuple[int, Any]:
        slug = _slug_from(path)
        if method == "GET" and path.endswith(WELL_KNOWN):
            card = gateway.agent_card(slug)
            return (200, card) if card else (404, {"error": f"no participant {slug!r}"})
        if method == "POST":
            message = json.loads(body or b"{}")
            return 200, (await gateway.rpc(message, slug) or {})
        return 404, {"error": f"no route for {method} {path}"}

    return route


def _slug_from(path: str) -> str | None:
    parts = [p for p in path.split("/") if p]
    return parts[1] if len(parts) >= 2 and parts[0] == "agents" else None


@app.command()
def schemes() -> None:
    """List the URI schemes this build can adapt."""
    for scheme in known_schemes():
        typer.echo(scheme)


async def _stream(session: Any, handle: str, affordance: str, arguments: dict[str, Any]) -> None:
    streamed = False
    async with aclosing(session.call(handle, affordance, arguments)) as stream:
        async for event in stream:
            if isinstance(event, Delta):
                sys.stdout.write(render.delta_text(event))
                sys.stdout.flush()
                streamed = True
            elif line := render.event_line(event):
                # Diagnostics go to stderr and must not disturb the stdout stream, so the
                # newline is cosmetic only - `streamed` still records what stdout has seen.
                if streamed:
                    sys.stdout.write("\n")
                typer.echo(line, err=True)

            if isinstance(event, Finished):
                if streamed:
                    sys.stdout.write("\n")
                elif event.result is not None:
                    typer.echo(render.result_text(event))
            elif isinstance(event, Failed):
                raise typer.Exit(1)


def _lookup(ws: Workspace, handle: str) -> Any:
    try:
        return ws.registry.get(handle)
    except UnknownParticipant:
        known = ", ".join(ws.registry.handles()) or "nothing yet"
        fail(f"no participant {handle!r}; known: {known}")


def _run(coro: Any) -> None:
    """Run a command, turning adapter failures into messages rather than tracebacks.

    Adapting a thing that is missing, misspelled or refusing to start is the single most
    common way to use this tool wrong; it should read as a sentence.
    """
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    except (AdapterError, InvalidURI, NothingReadable, InvalidAddress) as exc:
        fail(f"error: {exc}")


if __name__ == "__main__":
    app()
