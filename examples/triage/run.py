"""Five participants, one task, nothing in common.

A classifier stays a classifier, an MCP server stays an MCP server, a person stays a
person. The runtime routes between them, scopes what each can read, and stops at the one
step nobody should take unattended.

    uv run python -m examples.triage.run          # scripted approvals
    uv run python -m examples.triage.run --ask    # approve at the terminal
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from examples.triage.report import markdown, narrate
from maiku.adapters.channels import CallbackChannel, register_channel
from maiku.descriptor.enums import SideEffect
from maiku.runtime.escalation import route_to
from maiku.runtime.grants import Capability
from maiku.runtime.session import CallFailed
from maiku.runtime.workspace import Workspace

PARTICIPANTS = "python:examples.triage.participants"
FILES = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"
CLIP = b"a security camera clip, or near enough for a demo" * 4
FRAMES = 6

decisions: list[str] = []


def scripted_channel():
    async def answer(prompt, schema):
        return "yes"

    async def approve(reason, detail):
        decisions.append(reason)
        return True

    register_channel("scripted", lambda: CallbackChannel(answer, approve))


def say(step: str, detail: str = "") -> None:
    print(f"\n\033[1m{step}\033[0m" + (f"\n  {detail}" if detail else ""))


async def main(interactive: bool) -> int:
    scripted_channel()
    root = Path(tempfile.mkdtemp(prefix="maiku-triage-"))

    try:
        with Workspace(root) as workspace:
            say("adapting participants")
            channel = "cli" if interactive else "scripted"
            for uri in (PARTICIPANTS, FILES, f"human:reviewer?channel={channel}"):
                entry = (await workspace.add(uri)).entry
                kind = entry.descriptor.kind.value
                print(f"  {entry.handle:<22} {kind:<7} {len(entry.descriptor.affordances)} acts")

            for candidate in ("ollama:qwen3:8b", "ollama:llama3.2", "ollama:qwen2.5"):
                try:
                    entry = (await workspace.add(candidate)).entry
                except Exception:
                    continue
                if (await workspace.refresh(entry.handle)).online:
                    print(f"  {entry.handle:<22} model   local llm found")
                    break
                workspace.registry.remove(entry.handle)

            async with workspace.session(owner="demo") as session:
                session.responder = route_to(session, "human/reviewer")
                return await triage(session, workspace, interactive)
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def triage(session, workspace, interactive: bool) -> int:
    clip = await workspace.artifacts.write(CLIP, media_type="video/x-raw", name="clip.raw")
    say("a clip goes in", f"{clip.digest[:19]}...  {clip.size} bytes")

    # The classifier gets a grant that cannot publish, no matter what it decides to do.
    session.grant(
        "pipeline",
        capabilities=[
            Capability.parse("demo/vision#extract_frames"),
            Capability.parse("demo/vision#classify"),
            Capability.parse("demo/vision#tally"),
            Capability.parse("mcp/fixture#read_file"),
        ],
        scopes=set(),
        max_side_effect=SideEffect.WRITE,
    )

    say("splitting into frames", "a participant writing files, not text")
    frames = await session.result(
        "demo/vision",
        "extract_frames",
        {"clip": clip.digest, "count": FRAMES},
        caller="pipeline",
        readable={clip.digest},
    )
    print(f"  {len(frames)} frames, each an artifact reference")

    say("classifying", "tensors in, tensors out - no prompt anywhere")
    logits = []
    for digest in frames:
        tensor = await session.result(
            "demo/vision", "classify", {"frame": digest}, caller="pipeline", readable={digest}
        )
        logits.append(tensor["data"])
    print(f"  {len(logits)} logit vectors, dtype={tensor['dtype']} shape={tensor['shape']}")

    verdict = await session.result("demo/vision", "tally", {"logits": logits}, caller="pipeline")
    print(f"  verdict: {verdict['verdict']}  ({verdict['counts']})")

    say("reading context from an MCP server", "an existing tool, unchanged")
    notes = await session.result(
        "mcp/fixture", "read_file", {"path": "camera-notes.md"}, caller="pipeline"
    )
    print(f"  {notes}")

    say("writing the summary")
    prose, author = await narrate(session, verdict)
    print(f"  [{author}] {prose}")

    say("the pipeline tries to publish", "it holds no grant for this")
    try:
        await session.result("demo/vision", "publish", {"summary": "sneaky"}, caller="pipeline")
        print("  published - which should not have happened")
        return 1
    except CallFailed as refusal:
        print(f"  refused: {refusal.event.code}")

    say("the owner publishes", "irreversible, so a person is asked first")
    if interactive:
        print("  (you will be asked to approve)")
    digest = await session.result(
        "demo/vision", "publish", {"summary": markdown(verdict, prose, author)}
    )
    print(f"  approvals requested: {decisions or 'asked at the terminal'}")
    print("\n" + (await workspace.artifacts.read(digest)).decode())

    say("what the runtime recorded")
    for task in session.router.tasks.values():
        print(f"  {task.status.state.value:<10} {task.participant}#{task.affordance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--ask" in sys.argv)))
