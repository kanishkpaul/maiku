import pytest

from maiku.descriptor import Binding, Transport
from maiku.discovery.base import Address, Attempt, InvalidAddress, NotReadable, Reading


@pytest.mark.parametrize(
    ("raw", "url"),
    [
        ("https://device.local", "https://device.local"),
        ("192.168.1.42:8080", "http://192.168.1.42:8080"),
        ("device.local", "http://device.local"),
        ("http://host/base/", "http://host/base"),
    ],
)
def test_a_bare_address_is_reachable_without_a_scheme(raw, url):
    assert Address.parse(raw).url == url


@pytest.mark.parametrize("raw", ["", "   ", "http://"])
def test_an_address_without_a_host_is_refused(raw):
    with pytest.raises(InvalidAddress):
        Address.parse(raw)


def test_one_address_yields_one_handle_safe_slug():
    assert Address.parse("192.168.1.42:8080").slug == "192-168-1-42-8080"
    assert Address.parse("https://device.local").slug == "device-local"


def test_joining_a_path_does_not_double_the_separator():
    address = Address.parse("http://host")
    assert address.join("/openapi.json") == address.join("openapi.json")


def test_a_failed_reading_names_everything_it_tried():
    error = NotReadable(
        "openapi",
        [Attempt("http://host/openapi.json", "404"), Attempt("http://host/swagger.json", "404")],
    )
    assert "openapi.json -> 404" in str(error)
    assert "swagger.json -> 404" in str(error)
    assert len(error.attempts) == 2


def test_a_reading_is_not_a_descriptor():
    reading = Reading(
        source="openapi",
        affordances=[],
        binding=Binding(scheme="http", transport=Transport.HTTP, uri="http://host"),
    )
    assert not hasattr(reading, "id")
