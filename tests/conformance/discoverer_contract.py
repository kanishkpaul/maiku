"""The contract every discoverer must satisfy.

Mirrors `contract.py` for the same reason: many readers written to a convention become
many dialects, while many readers written to a suite stay one protocol.

Subclass and supply three fixtures: the discoverer, an address it should read, and an
address of some other protocol entirely.
"""

import pytest

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.binding import Binding
from maiku.discovery.assemble import discover
from maiku.discovery.base import Address, NotReadable, Reading

UNREACHABLE = Address.parse("http://127.0.0.1:1")


class DiscovererContract:
    @pytest.fixture
    def discoverer(self):
        raise NotImplementedError

    @pytest.fixture
    def readable(self) -> Address:
        raise NotImplementedError

    @pytest.fixture
    def foreign(self) -> Address:
        """An address serving something this discoverer does not read."""
        raise NotImplementedError

    def test_it_declares_a_name_and_a_precedence(self, discoverer):
        assert discoverer.name
        assert isinstance(discoverer.precedence, int)

    async def test_applies_is_false_rather_than_raising_on_an_unreachable_address(
        self, discoverer
    ):
        assert await discoverer.applies(UNREACHABLE) is False

    async def test_applies_is_false_for_another_protocol(self, discoverer, foreign):
        assert await discoverer.applies(foreign) is False

    async def test_applies_is_true_for_what_it_reads(self, discoverer, readable):
        assert await discoverer.applies(readable) is True

    async def test_applies_does_not_mutate(self, discoverer, readable):
        """Read twice: a check with a side effect is not a check."""
        assert await discoverer.applies(readable) is True
        assert await discoverer.applies(readable) is True

    async def test_read_returns_affordances_and_one_binding(self, discoverer, readable):
        reading = await discoverer.read(readable)
        assert isinstance(reading, Reading)
        assert reading.source == discoverer.name
        assert reading.affordances and all(
            isinstance(a, Affordance) for a in reading.affordances
        )
        assert isinstance(reading.binding, Binding)

    async def test_read_is_repeatable(self, discoverer, readable):
        first = await discoverer.read(readable)
        second = await discoverer.read(readable)
        assert [a.model_dump() for a in first.affordances] == [
            a.model_dump() for a in second.affordances
        ]

    async def test_read_raises_not_readable_carrying_what_it_tried(self, discoverer):
        with pytest.raises(NotReadable) as raised:
            await discoverer.read(UNREACHABLE)
        assert raised.value.source == discoverer.name
        assert raised.value.attempts

    async def test_it_assembles_into_a_descriptor_that_verifies_itself(
        self, discoverer, readable
    ):
        found = await discover(readable, [discoverer])
        payload = found.descriptor.model_dump(mode="json")
        assert type(found.descriptor)(**payload).id == found.descriptor.id
        assert found.sources == (discoverer.name,)

    async def test_assembly_with_no_affordances_raises_nothing_readable(self):
        from maiku.descriptor.enums import Transport
        from maiku.discovery.assemble import NothingReadable

        class EmptyDiscoverer:
            name = "empty"
            precedence = 10

            async def applies(self, address):
                return True

            async def read(self, address):
                return Reading(
                    source=self.name,
                    affordances=[],
                    binding=Binding(scheme="http", transport=Transport.HTTP),
                )

        with pytest.raises(NothingReadable):
            await discover(UNREACHABLE, [EmptyDiscoverer()])
