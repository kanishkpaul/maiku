import pytest

from maiku.adapters.uri import InvalidURI, ParticipantURI

_MCP_CMD = "npx -y @modelcontextprotocol/server-filesystem ./work"
_CARD = "https://host/.well-known/agent-card.json"


@pytest.mark.parametrize(
    ("raw", "scheme", "target"),
    [
        ("python:pkg.mod:fn", "python", "pkg.mod:fn"),
        ("ollama:qwen3:8b", "ollama", "qwen3:8b"),
        (f"mcp:{_MCP_CMD}", "mcp", _MCP_CMD),
        (f"a2a:{_CARD}", "a2a", _CARD),
    ],
)
def test_parses_scheme_and_target(raw, scheme, target):
    uri = ParticipantURI.parse(raw)
    assert (uri.scheme, uri.target) == (scheme, target)


def test_parses_query_params():
    uri = ParticipantURI.parse("human:kanishk?channel=cli&urgent=yes")
    assert uri.target == "kanishk"
    assert uri.param("channel") == "cli"
    assert uri.flag("urgent") is True
    assert uri.flag("missing", default=True) is True


def test_question_mark_without_assignment_stays_in_target():
    uri = ParticipantURI.parse("cli:grep -E 'a?b' file")
    assert uri.target == "grep -E 'a?b' file"
    assert uri.params == {}


def test_params_are_read_only():
    uri = ParticipantURI.parse("human:x?a=1")
    with pytest.raises(TypeError):
        uri.params["b"] = "2"  # type: ignore[index]


@pytest.mark.parametrize("raw", ["nocolon", ":empty", "bad scheme:x"])
def test_rejects_malformed(raw):
    with pytest.raises(InvalidURI):
        ParticipantURI.parse(raw)
