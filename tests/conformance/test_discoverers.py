"""Both discoverers against one address, through the shared contract."""

import pytest

from maiku.descriptor.enums import SideEffect
from maiku.discovery.assemble import EXTENSION_KEY, NothingReadable, discover
from maiku.discovery.base import Address
from maiku.discovery.mcp import MCPDiscoverer
from maiku.discovery.openapi import OpenAPIDiscoverer
from tests.conformance.discoverer_contract import DiscovererContract
from tests.fixtures.discovery_endpoint import BYTES_INPUT, HOST, client

DEVICE = Address.parse(HOST)
ELSEWHERE = Address.parse("http://device.local/nothing-here")


class TestOpenAPIDiscoverer(DiscovererContract):
    @pytest.fixture
    def discoverer(self):
        return OpenAPIDiscoverer(client=client())

    @pytest.fixture
    def readable(self):
        return DEVICE

    @pytest.fixture
    def foreign(self):
        return ELSEWHERE


class TestMCPDiscoverer(DiscovererContract):
    @pytest.fixture
    def discoverer(self):
        return MCPDiscoverer(client=client())

    @pytest.fixture
    def readable(self):
        return DEVICE

    @pytest.fixture
    def foreign(self):
        return ELSEWHERE


@pytest.fixture
def both():
    return [OpenAPIDiscoverer(client=client()), MCPDiscoverer(client=client())]


async def test_one_address_becomes_one_participant_with_two_bindings(both):
    found = await discover(DEVICE, both)
    descriptor = found.descriptor

    assert descriptor.handle == "auto/device-local"
    assert {b.scheme for b in descriptor.bindings} == {"http", "mcp"}
    assert found.sources == ("openapi", "mcp")
    assert descriptor.id == (await discover(DEVICE, both)).descriptor.id


async def test_affordances_from_both_readers_are_present(both):
    found = await discover(DEVICE, both)
    assert sorted(a.name for a in found.descriptor.affordances) == [
        "classify",
        "reboot",
        "status",
    ]


async def test_the_disagreement_goes_to_openapi_and_mcp_is_kept_verbatim(both):
    found = await discover(DEVICE, both)
    kept = found.descriptor.affordance("classify")

    assert "text" in kept.input_schema["properties"]
    [conflict] = found.descriptor.extensions[EXTENSION_KEY]["conflicts"]
    assert conflict["kept"] == "openapi"
    assert conflict["discarded_source"] == "mcp"
    assert conflict["discarded"]["input_schema"] == BYTES_INPUT


async def test_mcp_hints_survive_into_the_merged_descriptor(both):
    found = await discover(DEVICE, both)
    assert found.descriptor.affordance("reboot").side_effects is SideEffect.IRREVERSIBLE


async def test_each_binding_names_what_it_actually_serves(both):
    found = await discover(DEVICE, both)
    by_scheme = {b.scheme: b for b in found.descriptor.bindings}

    assert sorted(by_scheme["http"].affordances) == ["classify", "status"]
    # mcp lost `classify` on schema, so it stops claiming to serve it.
    assert by_scheme["mcp"].affordances == ["reboot"]
    assert found.descriptor.binding_for("classify").scheme == "http"
    assert found.descriptor.binding_for("reboot").scheme == "mcp"


async def test_a_total_failure_names_every_path_each_reader_tried(both):
    with pytest.raises(NothingReadable) as raised:
        await discover(Address.parse("http://device.local/absent"), both)

    message = str(raised.value)
    assert "/absent/openapi.json -> HTTP 404" in message
    assert "/absent/swagger.json -> HTTP 404" in message
    assert "/absent/mcp -> HTTP 404" in message
