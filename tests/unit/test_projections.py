import pytest

from maiku.descriptor import Affordance, AffordanceKind, SideEffect
from maiku.projections import a2a, mcp, openai_tools
from maiku.projections.naming import flatten, unflatten
from tests.conftest import make_descriptor


def test_flatten_round_trips(descriptor):
    name = flatten(descriptor.handle, "classify")
    assert name.isidentifier()
    assert unflatten(name) == ("local_sentiment", "classify")


def test_mcp_tool_carries_schema_and_routing_metadata(descriptor):
    tool = mcp.to_tools(descriptor)[0]
    assert tool["inputSchema"] == descriptor.affordance("classify").input_schema
    assert tool["outputSchema"] == descriptor.affordance("classify").output_schema
    assert tool["_meta"]["maiku/participant"] == descriptor.handle
    assert tool["_meta"]["maiku/affordance"] == "classify"


@pytest.mark.parametrize(
    ("effect", "read_only", "destructive", "open_world"),
    [
        (SideEffect.NONE, True, False, False),
        (SideEffect.READ, True, False, False),
        (SideEffect.WRITE, False, False, False),
        (SideEffect.EXTERNAL, False, False, True),
        (SideEffect.IRREVERSIBLE, False, True, True),
    ],
)
def test_side_effects_become_mcp_hints(effect, read_only, destructive, open_world):
    d = make_descriptor(
        affordances=[Affordance(name="act", summary="Do it", side_effects=effect)]
    )
    hints = mcp.to_tools(d)[0]["annotations"]
    assert hints["readOnlyHint"] is read_only
    assert hints["destructiveHint"] is destructive
    assert hints["openWorldHint"] is open_world


def test_openai_tool_shape(descriptor):
    tool = openai_tools.to_tools(descriptor)[0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == flatten(descriptor.handle, "classify")
    assert tool["function"]["parameters"]["required"] == ["text"]


def test_agent_card_has_required_a2a_fields(descriptor):
    card = a2a.to_agent_card(descriptor, base_url="https://host/a2a")
    for field in (
        "protocolVersion",
        "name",
        "description",
        "url",
        "version",
        "capabilities",
        "defaultInputModes",
        "defaultOutputModes",
        "skills",
    ):
        assert field in card
    assert card["skills"][0]["id"] == "classify"
    assert card["url"] == "https://host/a2a"


def test_streaming_capability_reflects_affordances():
    streamer = make_descriptor(
        affordances=[Affordance(name="talk", summary="Chat", kind=AffordanceKind.STREAM)]
    )
    assert a2a.to_agent_card(streamer)["capabilities"]["streaming"] is True
    assert a2a.to_agent_card(make_descriptor())["capabilities"]["streaming"] is False


def test_agent_card_round_trip_preserves_the_fields_a2a_carries(descriptor):
    card = a2a.to_agent_card(descriptor, base_url="https://host/a2a")
    revived = a2a.from_agent_card(card)
    again = a2a.to_agent_card(revived, base_url="https://host/a2a")

    assert again["name"] == card["name"]
    assert again["description"] == card["description"]
    assert again["version"] == card["version"]
    assert [s["id"] for s in again["skills"]] == [s["id"] for s in card["skills"]]
    assert again["defaultInputModes"] == card["defaultInputModes"]
    assert again["defaultOutputModes"] == card["defaultOutputModes"]


def test_ingested_agent_gets_message_shaped_input_not_a_fabricated_one():
    revived = a2a.from_agent_card(
        {
            "name": "Researcher",
            "description": "Finds things",
            "url": "https://host/a2a",
            "capabilities": {"streaming": True},
            "skills": [{"id": "search", "name": "Search the web"}],
        }
    )
    search = revived.affordance("search")
    assert search.input_schema == a2a.MESSAGE_INPUT_SCHEMA
    assert search.kind is AffordanceKind.STREAM
    assert revived.handle == "a2a/researcher"
    assert revived.bindings[0].uri == "https://host/a2a"
