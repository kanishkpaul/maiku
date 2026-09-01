"""D3: pointing maiku at an address, explicitly and as sugar."""

import pytest

from maiku.adapters.registry import coerce, known_schemes
from maiku.adapters.uri import InvalidURI


def test_auto_is_a_known_scheme():
    assert "auto" in known_schemes()


@pytest.mark.parametrize(
    "raw",
    [
        "auto:https://device.local",
        "auto:192.168.1.42:8080",
    ],
)
def test_the_explicit_form_is_taken_as_written(raw):
    uri = coerce(raw)
    assert uri.scheme == "auto"
    assert uri.target == raw.split(":", 1)[1]


@pytest.mark.parametrize(
    "raw",
    ["192.168.1.42", "192.168.1.42:8080", "https://device.local", "device.local", "localhost:8080"],
)
def test_a_bare_address_becomes_auto(raw):
    """The two invocations D3 reports as impossible."""
    assert coerce(raw).scheme == "auto"
    assert coerce(raw).target == raw


@pytest.mark.parametrize("raw", ["python:pkg.mod:fn", "ollama:qwen3:8b", "mcp:some-command"])
def test_a_known_scheme_is_never_reinterpreted_as_an_address(raw):
    assert coerce(raw).scheme == raw.split(":", 1)[0]


@pytest.mark.parametrize("raw", ["telepathy:brain", "nonsense"])
def test_a_mistyped_scheme_says_so_instead_of_becoming_a_host(raw):
    with pytest.raises(InvalidURI, match="no adapter for scheme"):
        coerce(raw)
