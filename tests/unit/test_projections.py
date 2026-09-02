import json

import pytest

from maiku.descriptor import Affordance, AffordanceKind, SideEffect
from maiku.projections import a2a, mcp, openai_tools
from maiku.projections.naming import flatten, unflatten
from maiku.runtime.grants import WILDCARD, Capability, Grant
from tests.conftest import everything, make_descriptor


def test_flatten_round_trips(descriptor):
    name = flatten(descriptor.handle, "classify")
    assert name.isidentifier()
    assert unflatten(name) == ("local_sentiment", "classify")


def test_mcp_tool_carries_schema_and_routing_metadata(descriptor, root):
    tool = mcp.to_tools(descriptor, root)[0]
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
    d = make_descriptor(affordances=[Affordance(name="act", summary="Do it", side_effects=effect)])
    hints = mcp.to_tools(d, everything())[0]["annotations"]
    assert hints["readOnlyHint"] is read_only
    assert hints["destructiveHint"] is destructive
    assert hints["openWorldHint"] is open_world


def test_openai_tool_shape(descriptor, root):
    tool = openai_tools.to_tools(descriptor, root)[0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == flatten(descriptor.handle, "classify")
    assert tool["function"]["parameters"]["required"] == ["text"]


def test_agent_card_has_required_a2a_fields(descriptor, root):
    card = a2a.to_agent_card(descriptor, root, base_url="https://host/a2a")
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
    assert a2a.to_agent_card(streamer, everything())["capabilities"]["streaming"] is True
    assert a2a.to_agent_card(make_descriptor(), everything())["capabilities"]["streaming"] is False


def test_agent_card_round_trip_preserves_the_fields_a2a_carries(descriptor, root):
    card = a2a.to_agent_card(descriptor, root, base_url="https://host/a2a")
    revived = a2a.from_agent_card(card)
    again = a2a.to_agent_card(revived, root, base_url="https://host/a2a")

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


def one_affordance(subject: str, capability: str, **narrower) -> Grant:
    return Grant(
        issuer="test",
        subject=subject,
        capabilities=[Capability.parse(capability)],
        scopes={WILDCARD},
        max_side_effect=narrower.pop("max_side_effect", SideEffect.IRREVERSIBLE),
        **narrower,
    )


def two_affordances():
    return make_descriptor(
        affordances=[
            Affordance(name="classify", summary="Label it"),
            Affordance(name="publish", summary="Post it", side_effects=SideEffect.IRREVERSIBLE),
        ]
    )


def test_the_root_grant_projects_every_affordance(root):
    descriptor = two_affordances()
    assert len(mcp.to_tools(descriptor, root)) == 2
    assert len(openai_tools.to_tools(descriptor, root)) == 2
    assert len(a2a.to_agent_card(descriptor, root)["skills"]) == 2


def test_a_grant_covering_one_affordance_projects_exactly_one_tool():
    descriptor = two_affordances()
    grant = one_affordance("caller", "local/sentiment#classify")

    [tool] = mcp.to_tools(descriptor, grant)
    assert tool["_meta"]["maiku/affordance"] == "classify"
    assert [s["id"] for s in a2a.to_agent_card(descriptor, grant)["skills"]] == ["classify"]


def test_an_affordance_a_caller_cannot_invoke_leaks_nothing_about_itself():
    """Not the name, not the schema, not the examples: a refused tool is not described."""
    descriptor = two_affordances()
    grant = one_affordance("caller", "local/sentiment#classify")
    rendered = json.dumps(
        [
            mcp.to_tools(descriptor, grant),
            openai_tools.to_tools(descriptor, grant),
            a2a.to_agent_card(descriptor, grant),
        ]
    )
    assert "publish" not in rendered
    assert "Post it" not in rendered


def test_a_grant_covering_nothing_projects_an_empty_list_not_an_error():
    descriptor = two_affordances()
    nobody = Grant(issuer="test", subject="stranger")

    assert mcp.to_tools(descriptor, nobody) == []
    assert openai_tools.to_tools(descriptor, nobody) == []
    assert a2a.to_agent_card(descriptor, nobody)["skills"] == []


def test_a_side_effect_ceiling_hides_what_sits_above_it():
    descriptor = two_affordances()
    careful = Grant(
        issuer="test",
        subject="guest",
        capabilities=[Capability()],
        scopes={WILDCARD},
        max_side_effect=SideEffect.READ,
    )
    assert [t["_meta"]["maiku/affordance"] for t in mcp.to_tools(descriptor, careful)] == [
        "classify"
    ]


def test_two_grants_on_one_descriptor_produce_different_tool_lists():
    descriptor = two_affordances()
    operator = mcp.to_tools(descriptor, everything("operator"))
    guest = mcp.to_tools(descriptor, one_affordance("guest", "local/sentiment#classify"))

    assert operator != guest
    assert len(operator) == 2 and len(guest) == 1


def test_an_expired_grant_describes_nothing():
    descriptor = two_affordances()
    lapsed = Grant(
        issuer="test",
        subject="late",
        capabilities=[Capability()],
        scopes={WILDCARD},
        max_side_effect=SideEffect.IRREVERSIBLE,
        expires_at=1.0,
    )
    assert mcp.to_tools(descriptor, lapsed) == []


def test_no_projection_accepts_a_descriptor_without_a_grant(descriptor):
    """Regression for D5: the grant is not optional, so it cannot be forgotten."""
    for project in (mcp.to_tools, openai_tools.to_tools, a2a.to_agent_card):
        with pytest.raises(TypeError):
            project(descriptor)
