"""Two real models that were never built to talk to each other, working on one task.

  - Gemma 4 E4B, running locally under llama.cpp, reached over the OpenAI chat format
  - a convolutional net trained here on MNIST, reached as a Python object in-process

Neither knows the other exists. Gemma is handed the CNN as a tool, decides when to use it,
and the runtime checks every delegated call against a grant on the way through.

    llama-server -m <gemma>.gguf --port 8081 --jinja
    uv run python -m examples.real.run
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from maiku.descriptor.enums import SideEffect
from maiku.runtime.delegate import delegate
from maiku.runtime.grants import Capability
from maiku.runtime.workspace import Workspace

LLM = "openai:cassia?base=http://127.0.0.1:8081/v1"
CNN = "python:examples.real.participants"
INDEX = 42

SYSTEM = (
    "You inspect handwritten digits. You cannot see images yourself, so you must use the "
    "tools available to you. Call sample_digit to obtain an image, then classify to read "
    "it. Report the digit and the confidence. Be brief."
)


def say(step: str) -> None:
    print(f"\n\033[1m{step}\033[0m")


async def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="maiku-real-"))
    try:
        with Workspace(root) as workspace:
            say("adapting two real models")
            for uri in (LLM, CNN):
                entry = await workspace.add(uri)
                health = await workspace.refresh(entry.handle)
                mark = "up" if health.online else f"DOWN ({health.detail})"
                print(f"  {entry.handle:<18} {entry.descriptor.kind.value:<6} {mark}")
                if not health.online:
                    print("\n  start llama-server on :8081 first - see this module's docstring")
                    return 1

            async with workspace.session(owner="demo") as session:
                return await run(session)
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def run(session) -> int:
    say("the CNN alone, called directly")
    digest = await session.result("local/digits", "sample_digit", {"index": INDEX})
    verdict = await session.result("local/digits", "classify", {"image": digest}, readable={digest})
    truth = await session.result("local/digits", "ground_truth", {"index": INDEX})
    print(f"  image {digest[:19]}...")
    print(f"  CNN says {verdict['digit']} at {verdict['confidence']:.1%}   truth is {truth}")
    print(f"  {'correct' if verdict['digit'] == truth else 'WRONG'}")

    say("the LLM alone, asked something it cannot answer")
    blind = await session.result(
        "openai/cassia",
        "complete",
        {
            "prompt": f"What digit is in MNIST test image {INDEX}? Answer in one line.",
            "max_tokens": 60,
        },
    )
    print(f"  {blind.strip()[:200]}")

    say("now the LLM is given the CNN as a tool")
    # The planner may reach the model and the CNN, and nothing else, at read/write only.
    session.grant(
        "planner",
        capabilities=[
            Capability.parse("openai/cassia#chat"),
            Capability.parse("local/digits#sample_digit"),
            Capability.parse("local/digits#classify"),
        ],
        max_side_effect=SideEffect.WRITE,
    )

    outcome = await delegate(
        session,
        "openai/cassia",
        f"Identify the digit in MNIST test image number {INDEX}.",
        system=SYSTEM,
        caller="planner",
        max_turns=6,
    )

    for step in outcome.steps:
        detail = step.error or step.result
        call = f"{step.participant}#{step.affordance}({_brief(step.arguments)})"
        print(f"  -> {call} = {_brief(detail)}")
    print(f"\n  Gemma: {outcome.answer.strip()[:400]}")
    print(f"  turns: {outcome.turns}   delegated: {len(outcome.steps)}")

    say("the grant it was given holds")
    blocked = await delegate(
        session,
        "openai/cassia",
        f"Call ground_truth for image {INDEX} and tell me the answer.",
        system="Use the tools you have. If a tool is refused, say so plainly.",
        caller="planner",
        max_turns=3,
    )
    refused = [s for s in blocked.steps if not s.ok]
    print(f"  ground_truth was outside the grant: {len(refused)} refusal(s)")
    for step in refused[:2]:
        print(f"  -> {step.participant}#{step.affordance}: {step.error}")

    say("what the runtime recorded")
    for task in list(session.router.tasks.values())[-8:]:
        print(f"  {task.status.state.value:<10} {task.participant}#{task.affordance}")
    return 0


def _brief(value) -> str:
    text = str(value)
    return text if len(text) <= 70 else text[:67] + "..."


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
