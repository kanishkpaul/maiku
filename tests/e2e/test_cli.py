import json
import sys

import pytest
from typer.testing import CliRunner

from maiku.cli.main import app

runner = CliRunner()
SAMPLE = "python:tests.fixtures.sample_module"
SERVER = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"


@pytest.fixture
def home(tmp_path):
    return ["--home", str(tmp_path / "home")]


def run(*args):
    result = runner.invoke(app, list(args))
    return result


@pytest.fixture
def stocked(home):
    assert run("add", SAMPLE, *home).exit_code == 0
    return home


def test_add_then_list(stocked):
    listing = run("ls", *stocked)
    assert listing.exit_code == 0
    assert "test/sample" in listing.stdout
    assert "in_process" in listing.stdout


def test_add_with_handle_override(home):
    assert run("add", SAMPLE, "--as", "mine/scorer", *home).exit_code == 0
    assert "mine/scorer" in run("ls", *home).stdout


def test_call_returns_a_result(stocked):
    result = run("call", "test/sample", "fetch", "-a", "key=abc", *stocked)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["value"] == "ABC"


def test_call_streams_text(stocked):
    result = run("call", "test/sample", "tokens", "-a", "text=a b", *stocked)
    assert result.exit_code == 0
    assert result.stdout.strip() == "ab"


def test_arguments_are_typed_where_they_parse(stocked):
    assert run("call", "test/sample", "narrate", "-a", "count=2", *stocked).exit_code == 0
    bad = run("call", "test/sample", "narrate", "-a", "count=lots", *stocked)
    assert bad.exit_code == 1


def test_json_arguments(stocked):
    result = run("call", "test/sample", "fetch", "--json", '{"key": "z"}', *stocked)
    assert json.loads(result.stdout)["key"] == "z"


def test_malformed_argument_is_a_clean_error(stocked):
    result = run("call", "test/sample", "fetch", "-a", "nokeyvalue", *stocked)
    assert result.exit_code == 1


def test_missing_participant_lists_what_is_known(stocked):
    result = run("call", "nope/nope", "x", *stocked)
    assert result.exit_code == 1
    assert "test/sample" in result.output


def test_adapting_something_absent_is_a_sentence_not_a_traceback(home):
    result = run("add", "python:no.such.module", *home)
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "cannot import" in result.output


def test_discovery_failure_is_a_sentence_not_a_traceback(home):
    result = run("add", "auto:http://127.0.0.1:1", *home)
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "nothing at http://127.0.0.1:1 could be read" in result.output


def test_unknown_scheme_is_reported(home):
    result = run("add", "telepathy:brain", *home)
    assert result.exit_code == 1
    assert "no adapter for scheme" in result.output


@pytest.mark.parametrize("fmt", ["maiku", "json", "mcp", "a2a", "openai"])
def test_describe_projects_into_each_format(stocked, fmt):
    result = run("describe", "test/sample", "--as", fmt, *stocked)
    assert result.exit_code == 0
    if fmt != "maiku":
        assert json.loads(result.stdout)


def test_describe_rejects_an_unknown_format(stocked):
    assert run("describe", "test/sample", "--as", "xml", *stocked).exit_code == 1


def test_find_searches_prose(stocked):
    assert "test/sample" in run("find", "countdown", *stocked).stdout
    assert "no participants" in run("find", "helicopter", *stocked).stdout


def test_probe_reports_reachability(stocked):
    result = run("probe", *stocked)
    assert result.exit_code == 0
    assert result.stdout.startswith("up")


def test_rm(stocked):
    assert run("rm", "test/sample", *stocked).exit_code == 0
    assert run("rm", "test/sample", *stocked).exit_code == 1


def test_schemes_lists_what_this_build_can_adapt():
    result = run("schemes")
    assert {"python", "mcp", "human", "ollama"} <= set(result.stdout.split())


def test_an_mcp_server_survives_the_whole_cli_path(home):
    assert run("add", SERVER, *home).exit_code == 0
    result = run("call", "mcp/fixture", "read_file", "-a", "path=x.md", *home)
    assert result.exit_code == 0
    assert result.stdout.strip() == "contents of x.md"


def test_a_streamed_result_is_not_also_printed_whole(stocked, monkeypatch):
    """A Usage or Log event arriving mid-stream must not make the result print twice."""
    from maiku.wire.events import Delta, Finished, Usage
    from maiku.wire.parts import TextPart

    async def fake_call(handle, affordance, arguments=None, **kwargs):
        yield Delta(part=TextPart(text="hello "), index=0)
        yield Delta(part=TextPart(text="world"), index=1)
        yield Usage(unit="token", amount=2)
        yield Finished(result="hello world")

    monkeypatch.setattr("maiku.runtime.session.Session.call", staticmethod(fake_call))
    result = run("call", "test/sample", "tokens", "-a", "text=x", *stocked)

    assert result.exit_code == 0
    assert result.stdout.count("hello world") == 1


def test_describe_defaults_to_the_operators_own_view(stocked):
    tools = json.loads(run("describe", "test/sample", "--as", "mcp", *stocked).stdout)
    assert len(tools) > 1


def test_describe_can_ask_what_one_caller_would_see(stocked):
    tools = json.loads(
        run(
            "describe", "test/sample", "--as", "mcp",
            "--grant", "test/sample#fetch", *stocked,
        ).stdout
    )
    assert [t["_meta"]["maiku/affordance"] for t in tools] == ["fetch"]


def test_a_caller_holding_nothing_sees_an_empty_projection(stocked):
    result = run(
        "describe", "test/sample", "--as", "openai", "--grant", "other/thing#nope", *stocked
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_serve_refuses_non_loopback_without_grant(home):
    result = run("serve", "a2a", "--host", "0.0.0.0", *home)
    assert result.exit_code == 1
    assert "refusing to serve root grant on non-loopback host" in result.output


def test_describe_json_and_maiku_formats_honour_grant(stocked):
    json_res = run(
        "describe", "test/sample", "--as", "json", "--grant", "test/sample#fetch", *stocked
    )
    assert json_res.exit_code == 0
    affs = [a["name"] for a in json.loads(json_res.stdout)["affordances"]]
    assert affs == ["fetch"]

    maiku_res = run(
        "describe", "test/sample", "--as", "maiku", "--grant", "test/sample#fetch", *stocked
    )
    assert maiku_res.exit_code == 0
    assert "fetch" in maiku_res.stdout
    assert "narrate" not in maiku_res.stdout


def test_describe_warns_on_mistyped_grant_spec(stocked):
    result = run("describe", "test/sample", "--as", "mcp", "--grant", "test/sampl#fetch", *stocked)
    assert result.exit_code == 0
    assert "note: --grant spec does not mention participant 'test/sample'" in result.output


def test_describe_json_with_grant_roundtrips_descriptor(stocked):
    from maiku.descriptor import ParticipantDescriptor

    json_res = run(
        "describe", "test/sample", "--as", "json", "--grant", "test/sample#fetch", *stocked
    )
    assert json_res.exit_code == 0
    payload = json.loads(json_res.stdout)
    rel_desc = ParticipantDescriptor(**payload)
    assert rel_desc.id == payload["id"]


def test_ls_prints_single_warning_line_per_unreadable_row(stocked):
    import sqlite3
    from pathlib import Path

    db_path = Path(stocked[1]) / "registry.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE participants SET descriptor = '{\"kind\": \"nope\"}'")
    conn.commit()
    conn.close()

    result = run("ls", *stocked)
    assert result.exit_code == 0
    warnings = [line for line in result.output.splitlines() if "warning: could not read" in line]
    assert len(warnings) == 1
    assert "validation error" in warnings[0]


def test_ls_prints_rederived_notice(stocked):
    import sqlite3
    from pathlib import Path

    db_path = Path(stocked[1]) / "registry.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT descriptor FROM participants WHERE handle = 'test/sample'"
    )
    row_json = cur.fetchone()[0]
    data = json.loads(row_json)
    data["id"] = "mk:" + "a" * 32
    conn.execute(
        "UPDATE participants SET descriptor = ? WHERE handle = 'test/sample'",
        (json.dumps(data),),
    )
    conn.commit()
    conn.close()

    result = run("ls", *stocked)
    assert result.exit_code == 0
    assert "notice: re-derived identity for test/sample" in result.output
