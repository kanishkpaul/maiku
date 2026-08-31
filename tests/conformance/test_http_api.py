"""Any REST API becomes a participant - with a spec, or without one."""

import httpx
import pytest

from maiku.adapters.openapi import read_spec, resolve_refs
from maiku.adapters.registry import open_participant
from maiku.descriptor.enums import Kind, SideEffect
from maiku.wire.events import Failed
from tests.conformance.contract import AdapterContract, drain

SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Widget API", "version": "2.1.0", "description": "Widgets, remotely"},
    "servers": [{"url": "https://api.widgets.test/v1"}],
    "components": {
        "schemas": {
            "Widget": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "size": {"type": "integer"}},
            }
        }
    },
    "paths": {
        "/widgets/{widget_id}": {
            "parameters": [{"name": "widget_id", "in": "path", "schema": {"type": "string"}}],
            "get": {
                "operationId": "getWidget",
                "summary": "Fetch one widget",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                        }
                    }
                },
            },
            "delete": {"operationId": "deleteWidget", "summary": "Destroy a widget"},
        },
        "/widgets": {
            "post": {
                "operationId": "createWidget",
                "summary": "Make a widget",
                "parameters": [{"name": "dry_run", "in": "query", "schema": {"type": "boolean"}}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"size": {"type": "integer"}},
                                "required": ["size"],
                            }
                        }
                    }
                },
            }
        },
    },
}

SPEC_URL = "https://api.widgets.test/openapi.json"
seen: dict = {}


def handler(request: httpx.Request) -> httpx.Response:
    seen["request"] = request
    if str(request.url) == SPEC_URL:
        return httpx.Response(200, json=SPEC)
    if request.url.path.startswith("/v1/widgets/") and request.method == "GET":
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "size": 4})
    if request.url.path == "/v1/widgets" and request.method == "POST":
        return httpx.Response(201, json={"created": True})
    if request.method == "DELETE":
        return httpx.Response(403, json={"error": "forbidden"})
    if request.url.path == "/bare":
        return httpx.Response(200, text="plain body")
    return httpx.Response(404)


def stub() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def spec_adapter(uri: str = f"http:{SPEC_URL}"):
    return (await open_participant(uri)).with_client(stub())


class TestOpenAPIParticipant(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await spec_adapter()
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "getwidget", {"widget_id": "w1"}


def test_local_refs_are_inlined():
    resolved = resolve_refs(SPEC, SPEC)
    schema = resolved["paths"]["/widgets/{widget_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["properties"]["size"] == {"type": "integer"}


def test_a_recursive_schema_degrades_instead_of_hanging():
    document = {"a": {"$ref": "#/a"}}
    assert resolve_refs(document, document) == {"a": {}}


def test_operations_are_read_from_paths():
    operations, info = read_spec(SPEC)
    assert info["title"] == "Widget API"
    assert {op.name for op in operations} == {"getwidget", "deletewidget", "createwidget"}


def test_path_level_parameters_are_inherited():
    operations, _ = read_spec(SPEC)
    delete = next(op for op in operations if op.name == "deletewidget")
    assert delete.path_params == ["widget_id"]
    assert delete.input_schema["required"] == ["widget_id"]


def test_a_json_body_is_flattened_into_arguments():
    operations, _ = read_spec(SPEC)
    create = next(op for op in operations if op.name == "createwidget")
    assert create.body_properties == ["size"]
    assert set(create.input_schema["properties"]) == {"size", "dry_run"}
    assert create.input_schema["required"] == ["size"]


async def test_descriptor_reflects_the_spec():
    descriptor = await (await spec_adapter()).describe()
    assert descriptor.kind is Kind.SERVICE
    assert descriptor.handle == "http/widget-api"
    assert descriptor.provenance.version == "2.1.0"
    assert descriptor.permissions.egress == ["https://api.widgets.test/v1"]


async def test_http_verbs_become_side_effects():
    descriptor = await (await spec_adapter()).describe()
    assert descriptor.affordance("getwidget").side_effects is SideEffect.READ
    assert descriptor.affordance("getwidget").idempotent
    assert descriptor.affordance("createwidget").side_effects is SideEffect.EXTERNAL
    assert descriptor.affordance("deletewidget").side_effects is SideEffect.IRREVERSIBLE


async def test_calling_an_operation_substitutes_the_path():
    adapter = await spec_adapter()
    events = await drain(adapter, "getwidget", {"widget_id": "w42"}, AdapterContract().context())
    assert events[-1].result == {"id": "w42", "size": 4}
    assert seen["request"].url.path == "/v1/widgets/w42"


async def test_body_and_query_arguments_are_routed_to_the_right_place():
    adapter = await spec_adapter()
    await drain(
        adapter,
        "createwidget",
        {"size": 9, "dry_run": True},
        AdapterContract().context(),
    )
    request = seen["request"]
    assert request.url.params["dry_run"] == "true"
    assert b'"size":9' in request.content.replace(b" ", b"")


async def test_an_error_status_becomes_a_failed_event():
    adapter = await spec_adapter()
    events = await drain(adapter, "deletewidget", {"widget_id": "w1"}, AdapterContract().context())
    assert isinstance(events[-1], Failed)
    assert "HTTP 403" in events[-1].message


async def test_an_api_with_no_spec_still_adapts():
    adapter = (
        await open_participant("http:https://api.widgets.test/bare?name=bare&affordance=fetch")
    ).with_client(stub())
    descriptor = await adapter.describe()

    assert descriptor.handle == "http/bare"
    assert [a.name for a in descriptor.affordances] == ["fetch"]

    events = await drain(adapter, "fetch", {}, AdapterContract().context())
    assert events[-1].result == "plain body"


async def test_probe_reports_a_dead_host():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    adapter = (await open_participant(f"http:{SPEC_URL}")).with_client(
        httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )
    assert not (await adapter.probe()).online


async def test_a_non_http_target_is_rejected():
    from maiku.adapters.base import AdapterError

    with pytest.raises(AdapterError):
        await open_participant("http:ftp://nope")
