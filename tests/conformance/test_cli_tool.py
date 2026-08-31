"""Any binary becomes a participant; the command template is the schema."""

import sys

import pytest

from maiku.adapters.cli_tool import build_schema, parse_slots
from maiku.adapters.registry import open_participant
from maiku.adapters.uri import InvalidURI
from maiku.descriptor.enums import AffordanceKind, Residency, SideEffect
from maiku.runtime.artifacts import ArtifactStore, ScopedArtifacts
from maiku.wire.events import ArtifactWritten, Delta, Failed
from tests.conformance.contract import AdapterContract, drain

ECHO = "cli:echo {message}?name=echo&effects=none&idempotent=true"


class TestCLITool(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant(ECHO)
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "run", {"message": "hello"}


def test_placeholders_become_a_schema():
    slots = parse_slots("resize {path} {width:integer} {out:artifact}")
    assert [(s.name, s.type) for s in slots] == [
        ("path", "string"),
        ("width", "integer"),
        ("out", "artifact"),
    ]

    schema = build_schema(slots)
    assert schema["properties"] == {"path": {"type": "string"}, "width": {"type": "integer"}}
    assert schema["required"] == ["path", "width"]


@pytest.mark.parametrize("template", ["cmd {a} {a}", "cmd {a:elephant}"])
def test_bad_templates_are_rejected(template):
    with pytest.raises(InvalidURI):
        parse_slots(template)


async def test_descriptor_reflects_the_uri_options():
    descriptor = await (await open_participant(ECHO)).describe()
    assert descriptor.handle == "cli/echo"
    assert descriptor.runtime.residency is Residency.SUBPROCESS
    run = descriptor.affordance("run")
    assert run.side_effects is SideEffect.NONE
    assert run.idempotent
    assert run.input_schema["required"] == ["message"]


async def test_running_a_command_returns_its_stdout():
    adapter = await open_participant(ECHO)
    events = await drain(adapter, "run", {"message": "hi there"}, AdapterContract().context())
    assert events[-1].result == "hi there"


async def test_arguments_are_never_a_second_command():
    adapter = await open_participant(ECHO)
    hostile = "x; echo pwned"
    events = await drain(adapter, "run", {"message": hostile}, AdapterContract().context())
    assert events[-1].result == hostile


async def test_a_nonzero_exit_becomes_a_failed_event():
    adapter = await open_participant(f"cli:{sys.executable} -c {{code}}?name=py")
    events = await drain(
        adapter, "run", {"code": "import sys; sys.exit(3)"}, AdapterContract().context()
    )
    assert isinstance(events[-1], Failed)
    assert "exited 3" in events[-1].message


async def test_json_output_is_parsed():
    adapter = await open_participant(f"cli:{sys.executable} -c {{code}}?name=py&json=true")
    events = await drain(
        adapter, "run", {"code": "print('{\"ok\": true}')"}, AdapterContract().context()
    )
    assert events[-1].result == {"ok": True}


async def test_streaming_mode_emits_a_delta_per_line():
    adapter = await open_participant(f"cli:{sys.executable} -u -c {{code}}?name=py&stream=true")
    descriptor = await adapter.describe()
    assert descriptor.affordance("run").kind is AffordanceKind.STREAM

    events = await drain(
        adapter,
        "run",
        {"code": "[print(i) for i in range(3)]"},
        AdapterContract().context(),
    )
    assert [e.part.text.strip() for e in events if isinstance(e, Delta)] == ["0", "1", "2"]


async def test_an_output_placeholder_becomes_an_artifact(tmp_path):
    adapter = await open_participant(
        f"cli:{sys.executable} -c {{code}} {{out:artifact}}?name=py&media_type=text/plain"
    )
    ctx = AdapterContract().context()
    store = ArtifactStore(tmp_path / "artifacts")
    ctx.artifacts = ScopedArtifacts(store)

    events = await drain(
        adapter,
        "run",
        {"code": "import sys; open(sys.argv[1], 'w').write('generated')"},
        ctx,
    )
    written = [e for e in events if isinstance(e, ArtifactWritten)]
    assert len(written) == 1
    assert await store.read(written[0].ref.digest) == b"generated"
    assert events[-1].result == written[0].ref.digest


async def test_probe_notices_a_missing_program():
    adapter = await open_participant("cli:definitely-not-a-binary-xyz {x}")
    assert not (await adapter.probe()).online
    assert (await open_participant(ECHO)).probe


async def test_unknown_affordance_is_reported_not_raised():
    adapter = await open_participant(ECHO)
    events = await drain(adapter, "nope", {}, AdapterContract().context())
    assert isinstance(events[-1], Failed)
    assert events[-1].code == "unknown_affordance"
