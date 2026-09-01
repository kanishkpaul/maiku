"""A paced, terminal-recordable demonstration of maiku's shared substrate.

This demo prints observable execution evidence rather than claiming access to private model
reasoning: inputs, participant calls, event streams, artifacts, decisions, and the resulting
session ledger are visible. It uses local Gemma as a narrator and a human-shaped reviewer
role, alongside a trained CNN, symbolic verifier, statistical calibrator, CLI, and MCP tools.

    uv run python -m examples.constellation.run
    uv run python -m examples.constellation.run --fast
    uv run python -m examples.constellation.run --pace 1.0
"""

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from contextlib import aclosing
from pathlib import Path
from typing import Any

from maiku.adapters.channels import CallbackChannel, register_channel
from maiku.runtime.workspace import Workspace
from maiku.wire.events import (
    ArtifactWritten,
    Delta,
    Failed,
    Finished,
    Progress,
    Started,
)
from maiku.wire.parts import TextPart

LLM = "openai:cassia?base=http://127.0.0.1:8081/v1"
CNN = "python:examples.real.participants"
RULES = "python:examples.constellation.participants:rule_verifier"
STATS = "python:examples.constellation.participants:confidence_calibrator"
MCP = f"mcp:{sys.executable} -u tests/fixtures/mcp_server.py"
NOTES = "cli:cat {path}?name=notebook&effects=read"
HUMAN = "human:llm-reviewer?channel=llm_reviewer"
INDEX = 42


def _short(value: Any, limit: int = 280) -> str:
    rendered = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    rendered = rendered.replace("\n", " ")
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def _say(title: str, detail: str = "") -> None:
    print(f"\n\033[1;36m{title}\033[0m")
    if detail:
        print(f"  \033[2m{detail}\033[0m")


async def _wait(pace: float, multiplier: float = 1.0) -> None:
    if pace:
        await asyncio.sleep(pace * multiplier)


async def _trace_call(
    session: Any,
    label: str,
    handle: str,
    affordance: str,
    arguments: dict[str, Any],
    pace: float,
) -> Any:
    """Run a call while rendering maiku's actual event stream for a recording."""
    print(f"\n  \033[1mCALL  {label}\033[0m")
    print(f"  route: {handle}#{affordance}")
    print(f"  input: {_short(arguments)}")
    started = time.perf_counter()
    result: Any = None

    async with aclosing(session.call(handle, affordance, arguments)) as stream:
        async for event in stream:
            elapsed = time.perf_counter() - started
            prefix = f"  [{elapsed:5.2f}s]"
            if isinstance(event, Started):
                print(f"{prefix} started: {event.participant}#{event.affordance}")
            elif isinstance(event, Progress):
                print(f"{prefix} progress: {event.message or 'working'}")
            elif isinstance(event, Delta):
                if isinstance(event.part, TextPart):
                    print(f"{prefix} stream: {event.part.text!r}")
                else:
                    print(f"{prefix} delta: {_short(event.part.model_dump(mode='json'))}")
            elif isinstance(event, ArtifactWritten):
                print(
                    f"{prefix} artifact: {event.ref.name or 'output'} "
                    f"{event.ref.digest[:20]}… ({event.ref.media_type})"
                )
            elif isinstance(event, Finished):
                result = event.result
                print(f"{prefix} finished: {_short(result)}")
            elif isinstance(event, Failed):
                message = f"{handle}#{affordance} failed: {event.code}: {event.message}"
                raise RuntimeError(message)
            else:
                print(f"{prefix} {event.type}: {_short(event.model_dump(mode='json'))}")
            await _wait(pace, 0.35)
    return result


def _llm_reviewer(session_box: dict[str, Any], pace: float) -> None:
    """Register a human-shaped role whose decision is explicitly LLM-simulated.

    DENY remains the default if Gemma does not follow the constrained approval format.
    """

    async def decide(prompt: str) -> str:
        return await _trace_call(
            session_box["session"],
            "LLM reviewer evaluates evidence",
            "openai/cassia",
            "complete",
            {
                "prompt": prompt,
                "system": (
                    "You are a cautious human reviewer simulation. "
                    "Follow the requested format exactly."
                ),
                "max_tokens": 24,
            },
            pace,
        )

    async def answer(prompt: str, schema: dict) -> str:
        del schema
        return await decide(f"Answer this review question in one concise sentence: {prompt}")

    async def approve(reason: str, detail: dict) -> bool:
        decision = await decide(
            "Act as the human reviewer for this request. Reply with exactly APPROVE or DENY, "
            "then a short reason. Approve only if the evidence is internally consistent. "
            f"Request: {reason}. Evidence: {detail}."
        )
        approved = decision.strip().upper().startswith("APPROVE")
        print(f"  reviewer decision: {'APPROVED' if approved else 'DENIED'}")
        return approved

    register_channel("llm_reviewer", lambda: CallbackChannel(answer, approve))


async def main(pace: float) -> int:
    session_box: dict[str, Any] = {}
    _llm_reviewer(session_box, pace)
    root = Path(tempfile.mkdtemp(prefix="maiku-constellation-"))
    notes = root / "field-notes.md"
    notes.write_text("Digit observations are logged nightly; retain measured confidence.\n")

    print("\033[1;35mMAIKU — MULTI-INTELLIGENCE LIVE TRACE\033[0m")
    print("A substrate demonstration: preserve native capabilities, unify execution.")
    print("Trace policy: visible calls and evidence, not invented private chain-of-thought.")
    print(f"Pacing: {pace:.2f}s per trace beat. Press Ctrl-C at any time to stop.")
    await _wait(pace, 1.5)

    try:
        with Workspace(root / "home") as workspace:
            _say("1 / 8  Discover and adapt distinct participants")
            sources = [
                ("local generative model", LLM, None),
                ("trained vision model", CNN, None),
                ("symbolic verifier", RULES, "logic/verifier"),
                ("confidence interpreter", STATS, "stats/calibrator"),
                ("CLI retrieval tool", NOTES, None),
                ("MCP tool server", MCP, None),
                ("LLM-as-human reviewer", HUMAN, None),
            ]
            for label, uri, handle in sources:
                entry = await workspace.add(uri, handle=handle)
                health = await workspace.refresh(entry.handle)
                affordances = ", ".join(item.name for item in entry.descriptor.affordances)
                print(f"  ✓ {label:<24} → {entry.handle}")
                print(
                    f"    kind={entry.descriptor.kind.value} "
                    f"up={health.online} acts=[{affordances}]"
                )
                await _wait(pace, 0.8)

            async with workspace.session(owner="demo") as session:
                session_box["session"] = session

                _say("2 / 8  CNN observes a real MNIST example")
                image = await _trace_call(
                    session,
                    "sample a real test digit",
                    "local/digits",
                    "sample_digit",
                    {"index": INDEX},
                    pace,
                )
                vision = await _trace_call(
                    session,
                    "CNN classifies the image",
                    "local/digits",
                    "classify",
                    {"image": image},
                    pace,
                )
                truth = await _trace_call(
                    session,
                    "retrieve independent ground truth",
                    "local/digits",
                    "ground_truth",
                    {"index": INDEX},
                    pace,
                )
                print(
                    f"\n  evidence summary: CNN digit={vision['digit']} "
                    f"confidence={vision['confidence']:.1%}; independent label={truth}"
                )
                await _wait(pace, 1.2)

                _say("3 / 8  Tools retrieve context and create an artifact")
                context = await _trace_call(
                    session,
                    "read local field notes",
                    "cli/notebook",
                    "run",
                    {"path": str(notes)},
                    pace,
                )
                chart = await _trace_call(
                    session,
                    "MCP server renders evidence chart",
                    "mcp/fixture",
                    "render_chart",
                    {"title": "digit evidence"},
                    pace,
                )
                print(f"\n  tool evidence: notes={context.strip()!r}; chart result={chart!r}")
                await _wait(pace, 1.2)

                _say("4 / 8  Symbolic verifier checks agreement")
                check = await _trace_call(
                    session,
                    "compare CNN claim with independent label",
                    "logic/verifier",
                    "rule_verifier",
                    {
                        "observed": vision["digit"],
                        "expected": truth,
                        "confidence": vision["confidence"],
                    },
                    pace,
                )
                print(f"\n  symbolic decision: {check['decision']} — {check['claim']}")
                await _wait(pace, 1.2)

                _say("5 / 8  Statistical calibrator interprets confidence")
                calibration = await _trace_call(
                    session,
                    "calibrate confidence after agreement check",
                    "stats/calibrator",
                    "confidence_calibrator",
                    {"confidence": vision["confidence"], "agrees": check["agrees"]},
                    pace,
                )
                print(f"\n  calibration: {calibration['band']} — {calibration['recommendation']}")
                await _wait(pace, 1.2)

                _say("6 / 8  Local Gemma plays the human reviewer role")
                approved = await _trace_call(
                    session,
                    "request human-shaped approval",
                    "human/llm-reviewer",
                    "approve",
                    {
                        "reason": "publish an evidence-grounded one-sentence finding",
                        "detail": {"verifier": check, "calibration": calibration},
                    },
                    pace,
                )
                print(f"\n  approval outcome: {approved}")
                await _wait(pace, 1.2)

                _say("7 / 8  Local Gemma narrates only established facts")
                prompt = (
                    "Write one factual sentence. Use only these facts; do not invent context. "
                    f"CNN digit={vision['digit']}; CNN confidence={vision['confidence']:.1%}; "
                    f"ground truth={truth}; verifier={check['decision']}; "
                    f"confidence band={calibration['band']}; notes={context.strip()!r}."
                )
                summary = await _trace_call(
                    session,
                    "generate evidence-grounded report",
                    "openai/cassia",
                    "complete",
                    {
                        "prompt": prompt,
                        "system": "Be concise, factual, and evidence-grounded.",
                        "max_tokens": 80,
                    },
                    pace,
                )
                print(f"\n  final report: {summary.strip()}")
                await _wait(pace, 1.3)

                _say("8 / 8  Inspect the shared runtime ledger")
                print(f"  tasks recorded: {len(session.router.tasks)}")
                for task in session.router.tasks.values():
                    print(f"  • {task.status.state.value:<10} {task.participant}#{task.affordance}")
                    await _wait(pace, 0.25)
                print(f"  blackboard posts recorded: {len(session.space)}")
                print("\n\033[1;32mDEMO COMPLETE\033[0m")
                print("  CNN + symbols + statistics + CLI + MCP + local LLM narrator/reviewer")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the paced maiku live demonstration.")
    parser.add_argument("--pace", type=float, default=0.7, help="Seconds between trace beats.")
    parser.add_argument("--fast", action="store_true", help="Disable deliberate recording pauses.")
    args = parser.parse_args()
    if args.pace < 0:
        parser.error("--pace must be zero or greater")
    if args.fast:
        args.pace = 0.0
    return args


if __name__ == "__main__":
    arguments = _arguments()
    raise SystemExit(asyncio.run(main(arguments.pace)))
