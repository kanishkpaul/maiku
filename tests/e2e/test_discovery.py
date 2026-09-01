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
