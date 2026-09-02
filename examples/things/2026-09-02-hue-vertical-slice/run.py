"""CNN -> local language model -> human approval -> Hue write -> Hue event."""

import argparse
import asyncio
import json
import os
import tempfile
import time
from contextlib import aclosing
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from maiku.adapters.hue import CHANGED, READ, WRITE
from maiku.runtime.escalation import route_to
from maiku.runtime.session import CallFailed
from maiku.runtime.workspace import Workspace
from maiku.wire.events import Delta, Event, Finished

LLM = "openai:cassia?base=http://127.0.0.1:8081/v1"
CNN = "python:examples.real.participants"
HUMAN = "human:reviewer?channel=cli"


def hue_uri() -> str:
    bridge = os.environ.get("HUE_BRIDGE_URL", "").rstrip("/")
    if not bridge:
        raise SystemExit("set HUE_BRIDGE_URL to the bridge's local https:// address")
    if not os.environ.get("HUE_APPLICATION_KEY"):
        raise SystemExit("set HUE_APPLICATION_KEY; credentials are never stored in the URI")
    params = {"key_env": "HUE_APPLICATION_KEY"}
    if light := os.environ.get("HUE_LIGHT_ID"):
        params["light"] = light
    return f"hue:{bridge}?{urlencode(params)}"


async def watch_one_change(session: Any, handle: str) -> dict[str, Any] | None:
    observed = None
    async with aclosing(session.call(handle, CHANGED)) as stream:
        async for event in stream:
            if isinstance(event, Delta):
                observed = event.part.data
                task = next(
                    task
                    for task in session.router.tasks.values()
                    if task.participant == handle and task.affordance == CHANGED and not task.done
                )
                session.router.cancel(task.id)
            if observed is not None and isinstance(event, Finished):
                return observed
    return observed


def write_trace(
    path: Path,
    observed_events: list[dict[str, Any]],
    session: Any,
    summary: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"record": "event", **event} for event in observed_events
    ] + [
        {"record": "task", **task.model_dump(mode="json")}
        for task in session.router.tasks.values()
    ] + [{"record": "summary", **summary}]
    path.write_text("".join(json.dumps(record, default=str) + "\n" for record in records))


async def main(index: int, trace_path: Path) -> int:
    sources = [LLM, CNN, HUMAN, hue_uri()]
    observed_events: list[dict[str, Any]] = []

    def observe(session_id: str, event: Event) -> None:
        observed_events.append(
            {"session_id": session_id, **event.model_dump(mode="json")}
        )

    with Workspace(Path(tempfile.mkdtemp(prefix="maiku-hue-")) / "home") as workspace:
        entries = []
        for source in sources:
            entry = (await workspace.add(source)).entry
            health = await workspace.refresh(entry.handle)
            if not health.online:
                raise SystemExit(f"{entry.handle} is down: {health.detail}")
            entries.append(entry)
            print(f"adapted {entry.handle:<20} {entry.descriptor.kind.value}")

        hue = next(entry for entry in entries if entry.handle.startswith("hue/"))
        async with workspace.session(owner="demo", observer=observe) as session:
            session.responder = route_to(session, "human/reviewer")

            before = await session.result(hue.handle, READ)
            digest = await session.result("local/digits", "sample_digit", {"index": index})
            verdict = await session.result("local/digits", "classify", {"image": digest})
            proposed = {
                "on": True,
                "brightness": max(10.0, round(verdict["confidence"] * 100, 1)),
            }
            rationale = await session.result(
                "openai/cassia",
                "complete",
                {
                    "prompt": (
                        f"A CNN classified handwritten digit {verdict['digit']} with "
                        f"confidence {verdict['confidence']:.1%}. In one sentence, explain "
                        f"why a human might approve turning a status light on at "
                        f"{proposed['brightness']}% brightness. Do not claim you saw the image."
                    ),
                    "max_tokens": 80,
                },
            )

            print(f"CNN: {verdict}")
            print(f"model: {rationale.strip()}")
            print(f"Hue before: {before}; proposed: {proposed}")
            print("The Hue write now routes to human/reviewer for approval.")

            watcher = asyncio.create_task(watch_one_change(session, hue.handle))
            await asyncio.sleep(0.25)
            try:
                after = await session.result(hue.handle, WRITE, proposed)
            except CallFailed as exc:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                write_trace(
                    trace_path,
                    observed_events,
                    session,
                    {"approved": False, "reason": str(exc)},
                )
                print(f"write did not happen: {exc}")
                print(f"trace: {trace_path}")
                return 2

            try:
                changed = await asyncio.wait_for(watcher, timeout=10.0)
            except TimeoutError:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                changed = None

            summary = {
                "approved": True,
                "cnn": verdict,
                "model_rationale": rationale.strip(),
                "hue_before": before,
                "hue_after": after,
                "hue_event": changed,
            }
            write_trace(trace_path, observed_events, session, summary)
            print(f"Hue after: {after}")
            print(f"Hue event: {changed or 'no event arrived within 10 seconds'}")
            print(f"trace: {trace_path}")
            return 0 if changed is not None else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, default=42)
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path(tempfile.gettempdir()) / f"maiku-hue-{int(time.time())}.jsonl",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.index, args.trace)))
