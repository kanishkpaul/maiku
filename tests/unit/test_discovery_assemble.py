import pytest

from maiku.descriptor import Affordance, Binding, Display, Transport
from maiku.discovery.assemble import EXTENSION_KEY, NothingReadable, discover
from maiku.discovery.base import Address, Attempt, NotReadable, Reading

ADDRESS = Address.parse("http://device.local")

TEXT_IN = {"type": "object", "properties": {"text": {"type": "string"}}}
NUMBER_IN = {"type": "object", "properties": {"n": {"type": "number"}}}
SPEC_MISS = Attempt("/openapi.json", "404")


def affordance(name: str, input_schema=None) -> Affordance:
    return Affordance(name=name, summary=name, input_schema=input_schema or TEXT_IN)


class Fake:
    """A discoverer that answers from memory, so assembly can be tested without sockets."""

    def __init__(self, name, precedence, affordances=(), applies=True, failure=None):
        self.name = name
        self.precedence = precedence
        self._affordances = list(affordances)
        self._applies = applies
        self._failure = failure

    async def applies(self, address):
        if isinstance(self._applies, BaseException):
            raise self._applies
        return self._applies

    async def read(self, address):
        if self._failure is not None:
            raise self._failure
        return Reading(
            source=self.name,
            affordances=self._affordances,
            binding=Binding(scheme=self.name, transport=Transport.HTTP, uri=address.url),
            display=Display(name=self.name),
        )


async def test_two_discoverers_make_one_participant_with_two_bindings():
    found = await discover(
        ADDRESS,
        [
            Fake("openapi", 30, [affordance("classify")]),
            Fake("mcp", 20, [affordance("summarise")]),
        ],
    )
    assert found.descriptor.handle == "auto/device-local"
    assert len(found.descriptor.bindings) == 2
    assert sorted(a.name for a in found.descriptor.affordances) == ["classify", "summarise"]
    assert found.sources == ("openapi", "mcp")


async def test_the_assembled_descriptor_verifies_its_own_id():
    found = await discover(ADDRESS, [Fake("openapi", 30, [affordance("classify")])])
    payload = found.descriptor.model_dump(mode="json")
    assert type(found.descriptor)(**payload).id == found.descriptor.id


async def test_an_agreed_affordance_is_kept_once_without_a_conflict():
    found = await discover(
        ADDRESS,
        [Fake("openapi", 30, [affordance("classify")]), Fake("mcp", 20, [affordance("classify")])],
    )
    assert [a.name for a in found.descriptor.affordances] == ["classify"]
    assert found.descriptor.extensions == {}


async def test_a_schema_conflict_goes_to_precedence_and_is_recorded_verbatim():
    loser = affordance("classify", NUMBER_IN)
    found = await discover(
        ADDRESS,
        [Fake("mcp", 20, [loser]), Fake("openapi", 30, [affordance("classify")])],
    )
    kept = found.descriptor.affordance("classify")
    assert kept.input_schema == TEXT_IN

    [conflict] = found.descriptor.extensions[EXTENSION_KEY]["conflicts"]
    assert conflict["kept"] == "openapi"
    assert conflict["discarded_source"] == "mcp"
    assert conflict["discarded"] == loser.model_dump(mode="json")


async def test_one_discoverer_failing_does_not_fail_the_discovery():
    found = await discover(
        ADDRESS,
        [
            Fake("openapi", 30, [affordance("classify")]),
            Fake("mcp", 20, failure=NotReadable("mcp", [Attempt("/mcp", "404")])),
        ],
    )
    assert [a.name for a in found.descriptor.affordances] == ["classify"]
    assert [f.source for f in found.failures] == ["mcp"]


async def test_a_total_failure_names_every_source_tried():
    with pytest.raises(NothingReadable) as raised:
        await discover(
            ADDRESS,
            [
                Fake("openapi", 30, failure=NotReadable("openapi", [SPEC_MISS])),
                Fake("mcp", 20, applies=False),
                Fake("wot", 40, applies=RuntimeError("boom")),
            ],
        )
    message = str(raised.value)
    assert "openapi" in message and "/openapi.json -> 404" in message
    assert "mcp: does not apply" in message
    assert "wot" in message and "raised" in message


async def test_discovery_against_one_address_is_repeatable():
    def run():
        return discover(
            ADDRESS,
            [
                Fake("openapi", 30, [affordance("classify")]),
                Fake("mcp", 20, [affordance("classify", NUMBER_IN)]),
            ],
        )

    first, second = (await run()).descriptor, (await run()).descriptor
    assert first.id == second.id


async def test_an_explicit_handle_is_chosen_once_not_per_discoverer():
    found = await discover(
        ADDRESS,
        [Fake("openapi", 30, [affordance("classify")]), Fake("mcp", 20, [affordance("go")])],
        handle="mine/thing",
    )
    assert found.descriptor.handle == "mine/thing"


async def test_provenance_names_every_discoverer_that_contributed():
    found = await discover(
        ADDRESS,
        [Fake("openapi", 30, [affordance("classify")]), Fake("mcp", 20, [affordance("go")])],
    )
    assert found.descriptor.provenance.adapter == "discovery(openapi+mcp)"
    assert found.descriptor.provenance.source_uri == ADDRESS.url
