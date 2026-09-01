"""Three real intelligences and a person, working on one task.

  - Gemma 4 E4B, running locally under llama.cpp, reached over the OpenAI chat format
  - a convolutional net trained here on MNIST, reached as a Python object in-process
  - Anthropic's MCP filesystem server, unmodified, reached over JSON-RPC on stdio
  - a human, reached at a terminal

None of them was built to work with the others. Gemma is handed the other two as tools,
decides what to call, and every delegated call is checked against a grant on the way
through. The one irreversible step stops for a person.

    llama-server -m <gemma>.gguf --port 8081 --jinja
    uv run python -m examples.real.run          # scripted approvals
    uv run python -m examples.real.run --ask    # approve at the terminal
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from maiku.adapters.channels import CallbackChannel, register_channel
from maiku.descriptor.enums import SideEffect
from maiku.runtime.delegate import delegate
from maiku.runtime.escalation import route_to
from maiku.runtime.grants import Capability
from maiku.runtime.workspace import Workspace

LLM = "openai:cassia?base=http://127.0.0.1:8081/v1"
CNN = "python:examples.real.participants"
INDEX = 42

SYSTEM = (
    "You inspect handwritten digits and file reports. You cannot see images yourself, so "
    "you must use your tools. To read a digit: call sample_digit to get an image, then "
    "classify to read it. To file a report, use write_file. Be brief and factual."
)

approvals: list[str] = []


def scripted() -> None:
    async def answer(prompt, schema):
        return "yes"

    async def approve(reason, detail):
        approvals.append(reason)
        return True

    register_channel("scripted", lambda: CallbackChannel(answer, approve))


def say(step: str) -> None:
    print(f"\n\033[1m{step}\033[0m")


def brief(value, width: int = 66) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 3] + "..."


async def main(interactive: bool) -> int:
    scripted()
    root = Path(tempfile.mkdtemp(prefix="maiku-real-"))
    work = root / "work"
    work.mkdir()
    (work / "notes.md").write_text("camera 3 faces the loading bay; digits logged nightly\n")

    channel = "cli" if interactive else "scripted"
    sources = [
        LLM,
        CNN,
        f"mcp:npx -y @modelcontextprotocol/server-filesystem {work}?name=files&approval=on_scope",
        f"human:reviewer?channel={channel}",
    ]

    try:
        with Workspace(root / "home") as workspace:
            say("adapting four participants")
            for uri in sources:
                entry = (await workspace.add(uri)).entry
                health = await workspace.refresh(entry.handle)
                mark = "up" if health.online else f"DOWN ({health.detail})"
                print(
                    f"  {entry.handle:<16} {entry.descriptor.kind.value:<6} "
                    f"{len(entry.descriptor.affordances):>2} acts  {mark}"
                )
                if not health.online:
                    print("\n  start llama-server on :8081 - see this module's docstring")
                    return 1

            async with workspace.session(owner="demo") as session:
                session.responder = route_to(session, "human/reviewer")
                return await run(session, work, interactive)
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def run(session, work: Path, interactive: bool) -> int:
    say("the CNN on its own, to establish ground truth")
    digest = await session.result("local/digits", "sample_digit", {"index": INDEX})
    verdict = await session.result("local/digits", "classify", {"image": digest})
    truth = await session.result("local/digits", "ground_truth", {"index": INDEX})
    print(f"  CNN reads {verdict['digit']} at {verdict['confidence']:.1%}, truth is {truth}")

    say("the LLM on its own, asked the same thing")
    blind = await session.result(
        "openai/cassia",
        "complete",
        {"prompt": f"Which digit is in MNIST test image {INDEX}? One line.", "max_tokens": 60},
    )
    print(f"  {blind.strip()[:180]}")

    say("now the LLM is given the other two as tools")
    session.grant(
        "planner",
        capabilities=[
            Capability.parse("openai/cassia#chat"),
            Capability.parse("local/digits#sample_digit"),
            Capability.parse("local/digits#classify"),
            Capability.parse("mcp/files#read_text_file"),
            Capability.parse("mcp/files#write_file"),
        ],
        max_side_effect=SideEffect.IRREVERSIBLE,
    )

    outcome = await delegate(
        session,
        "openai/cassia",
        f"Read notes.md for context, identify the digit in MNIST test image {INDEX}, "
        f"then write a one-paragraph report to report.md.",
        system=SYSTEM,
        caller="planner",
        max_turns=8,
    )

    for step in outcome.steps:
        mark = " " if step.ok else "x"
        call = f"{step.participant}#{step.affordance}"
        print(f"  {mark} {call:<28} {brief(step.error or step.result)}")

    print(f"\n  Gemma: {outcome.answer.strip()[:300]}")
    print(f"  turns {outcome.turns}, delegated {len(outcome.steps)}")

    say("the irreversible step stopped for a person")
    print(f"  approvals asked: {approvals or 'asked at the terminal'}")

    report = work / "report.md"
    if report.exists():
        print(f"\n  {report.name} on disk, written by the model through MCP:")
        for line in report.read_text().splitlines()[:6]:
            print(f"    {line}")
    else:
        print("  no report was written")

    say("what the grant refused")
    blocked = await delegate(
        session,
        "openai/cassia",
        f"Call ground_truth for image {INDEX}, then delete notes.md.",
        system="Use your tools. If one is refused, say so plainly and stop.",
        caller="planner",
        max_turns=3,
    )
    refused = [s for s in blocked.steps if not s.ok]
    print(f"  {len(refused)} refusal(s) - neither tool was in the grant")
    for step in refused[:3]:
        print(f"  x {step.participant}#{step.affordance}: {brief(step.error, 80)}")

    say("what the runtime recorded")
    for task in list(session.router.tasks.values())[-10:]:
        print(f"  {task.status.state.value:<10} {task.participant}#{task.affordance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--ask" in sys.argv)))
