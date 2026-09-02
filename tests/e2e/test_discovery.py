"""Stage 3 end to end: one address, one participant, two bindings."""

import pytest
from typer.testing import CliRunner

from maiku.adapters.registry import open_participant
from maiku.cli.main import app
from maiku.discovery.assemble import EXTENSION_KEY
from maiku.runtime.workspace import Workspace

runner = CliRunner()


@pytest.fixture
def device():
    from tests.fixtures.discovery_server import serving

    with serving() as url:
        yield url


async def test_two_discoverers_on_one_address_make_one_participant(device, tmp_path):
    with Workspace(tmp_path / "home") as workspace:
        registered = await workspace.add(f"auto:{device}")
        descriptor = registered.entry.descriptor

        assert {b.scheme for b in descriptor.bindings} == {"http", "mcp"}
        assert sorted(a.name for a in descriptor.affordances) == ["classify", "reboot", "status"]
        assert len(workspace.registry.list()) == 1


async def test_the_conflict_is_recorded_rather_than_dropped(device):
    adapter = await open_participant(f"auto:{device}")
    try:
        descriptor = await adapter.describe()
    finally:
        await adapter.close()

    [conflict] = descriptor.extensions[EXTENSION_KEY]["conflicts"]
    assert conflict["affordance"] == "classify"
    assert conflict["kept"] == "openapi"
    assert conflict["discarded_source"] == "mcp"


async def test_a_bare_address_needs_no_scheme_knowledge(device, tmp_path):
    """`http:` is one of maiku's own schemes, so the sugar is tested without one."""
    with Workspace(tmp_path / "home") as workspace:
        registered = await workspace.add(device.removeprefix("http://"))
        assert registered.entry.descriptor.handle.startswith("auto/127-0-0-1-")


async def test_discovering_the_same_address_twice_is_the_same_participant(device, tmp_path):
    with Workspace(tmp_path / "home") as workspace:
        first = await workspace.add(f"auto:{device}")
        second = await workspace.add(f"auto:{device}")
        assert second.identity_changed is False
        assert first.entry.descriptor.id == second.entry.descriptor.id


def test_the_cli_adds_lists_and_describes_it_once(device, tmp_path):
    home = ["--home", str(tmp_path / "home")]

    added = runner.invoke(app, ["add", f"auto:{device}", *home])
    assert added.exit_code == 0, added.output

    listing = runner.invoke(app, ["ls", *home])
    assert listing.stdout.count("auto/127-0-0-1-") == 1

    handle = "auto/127-0-0-1-" + device.rsplit(":", 1)[1]
    described = runner.invoke(app, ["describe", handle, *home])
    assert described.exit_code == 0, described.output
    assert "http" in described.stdout and "mcp" in described.stdout


def test_http_url_and_host_port_coercion():
    from maiku.adapters.registry import coerce
    from maiku.adapters.uri import InvalidURI, ParticipantURI

    assert coerce("http://device.local") == ParticipantURI.parse("auto:http://device.local")
    assert coerce("https://device.local") == ParticipantURI.parse("auto:https://device.local")
    assert coerce("http:https://api.com/spec.json") == ParticipantURI.parse("http:https://api.com/spec.json")

    assert coerce("raspberrypi:8080") == ParticipantURI.parse("auto:raspberrypi:8080")
    with pytest.raises(InvalidURI, match="no adapter for scheme 'ollma'"):
        coerce("ollma:qwen3")


async def test_binding_that_won_no_affordances_serves_none():
    from maiku.descriptor.affordance import Affordance
    from maiku.descriptor.binding import Binding, Transport
    from maiku.descriptor.enums import AffordanceKind, Determinism, LatencyClass, SideEffect
    from maiku.discovery.assemble import discover
    from maiku.discovery.base import Address, Reading

    a1 = Affordance(
        name="classify",
        summary="s1",
        description="d1",
        kind=AffordanceKind.INVOKE,
        input_schema={"type": "string"},
        output_schema={},
        determinism=Determinism.DETERMINISTIC,
        latency_class=LatencyClass.SECONDS,
        idempotent=True,
        side_effects=SideEffect.READ,
    )
    a2 = Affordance(
        name="classify",
        summary="s2",
        description="d2",
        kind=AffordanceKind.INVOKE,
        input_schema={"type": "number"},
        output_schema={},
        determinism=Determinism.DETERMINISTIC,
        latency_class=LatencyClass.SECONDS,
        idempotent=True,
        side_effects=SideEffect.READ,
    )

    class D1:
        name = "openapi"
        precedence = 30

        async def applies(self, address):
            return True

        async def read(self, address):
            b = Binding(scheme="http", transport=Transport.HTTP)
            return Reading(source="openapi", affordances=[a1], binding=b)

    class D2:
        name = "mcp"
        precedence = 20

        async def applies(self, address):
            return True

        async def read(self, address):
            b = Binding(scheme="mcp", transport=Transport.STDIO)
            return Reading(source="mcp", affordances=[a2], binding=b)

    found = await discover(Address.parse("http://127.0.0.1"), [D1(), D2()])
    mcp_binding = next(b for b in found.descriptor.bindings if b.scheme == "mcp")
    assert mcp_binding.affordances == []
    assert mcp_binding.serves("classify") is False
