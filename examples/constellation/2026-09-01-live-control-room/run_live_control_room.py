# ruff: noqa: E501
"""Live browser control room for the Maiku constellation demonstration.

Run with:
    uv run --extra web --extra net --extra torch examples/constellation/2026-09-01-live-control-room/run_live_control_room.py

The browser does not emulate the runtime. It calls this local control plane, which adapts
real participants into one Workspace and relays their actual Maiku event streams over SSE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from maiku.adapters.channels import CallbackChannel, register_channel
from maiku.runtime.workspace import Workspace
from maiku.wire.events import (
    ArtifactWritten,
    Delta,
    Event,
    Failed,
    Finished,
    NeedsApproval,
    NeedsInput,
)
from maiku.wire.parts import TextPart

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / ".maiku-live-demo"


@dataclass(frozen=True)
class Recipe:
    key: str
    title: str
    category: str
    description: str
    uri: str
    handle: str


class HumanResponse(BaseModel):
    request_id: str
    value: str | bool


class ControlRoom:
    def __init__(self, pace: float) -> None:
        self.pace = pace
        self.listeners: set[asyncio.Queue[dict[str, Any]]] = set()
        self.pending: dict[str, asyncio.Future[Any]] = {}
        self.pending_details: dict[str, dict[str, Any]] = {}
        self.run_task: asyncio.Task[None] | None = None
        self.session: Any | None = None
        self.started_at: float | None = None
        self.case_dir = RUNTIME_ROOT / "casebook"
        self._prepare_casebook()
        self.workspace = Workspace(RUNTIME_ROOT / "workspace")
        self.recipes = self._recipes()
        register_channel("browser", lambda: CallbackChannel(self._browser_answer, self._browser_approve))

    def _prepare_casebook(self) -> None:
        self.case_dir.mkdir(parents=True, exist_ok=True)
        (self.case_dir / "case-notes.md").write_text(
            "# Loading-bay digit evidence\n\n"
            "A calibration placard was photographed during the nightly loading-bay check. "
            "The report may state a digit only when the vision result, independent label, and "
            "rule verification agree. Preserve the measured confidence and do not infer a cause.\n"
        )

    def _recipes(self) -> list[Recipe]:
        casebook = Path(__file__).with_name("live_control_room_casebook_mcp.py")
        return [
            Recipe("gemma", "Gemma / cassia", "language model", "Local Gemma over the OpenAI-compatible llama.cpp server.", "openai:cassia?base=http://127.0.0.1:8081/v1", "openai/cassia"),
            Recipe("cnn", "DigitCNN", "vision model", "A trained PyTorch CNN that reads and writes real image artifacts.", "python:examples.real.participants", "local/digits"),
            Recipe("verifier", "Rule verifier", "symbolic intelligence", "A deterministic checker that compares observation with independent ground truth.", "python:examples.constellation.participants:rule_verifier", "logic/verifier"),
            Recipe("calibrator", "Confidence calibrator", "statistical pipeline", "A conservative interpreter of confidence after the agreement check.", "python:examples.constellation.participants:confidence_calibrator", "stats/calibrator"),
            Recipe("casebook", "Casebook MCP", "tool server", "A real local stdio MCP server for evidence, charts, and the approval-gated report.", f"mcp:{sys.executable} -u {casebook} --case-dir {self.case_dir}?name=casebook&approval=on_scope", "mcp/casebook"),
            Recipe("human", "You", "human", "A browser-backed human participant who chooses and approves in the shared runtime.", "human:reviewer?channel=browser", "human/reviewer"),
        ]

    def snapshot(self) -> dict[str, Any]:
        entries = {entry.handle: entry for entry in self.workspace.registry.list()}
        participants = []
        for recipe in self.recipes:
            entry = entries.get(recipe.handle)
            participants.append({
                "key": recipe.key,
                "title": recipe.title,
                "category": recipe.category,
                "description": recipe.description,
                "handle": recipe.handle,
                "added": entry is not None,
                "online": entry.online if entry else False,
                "affordances": [item.name for item in entry.descriptor.affordances] if entry else [],
                "health": entry.health.detail if entry and entry.health else None,
            })
        return {
            "participants": participants,
            "ready": all(item["added"] and item["online"] for item in participants),
            "running": self.run_task is not None and not self.run_task.done(),
            "pending": self._pending_payload(),
            "pace": self.pace,
            "reportPath": str(self.case_dir / "reports" / "evidence-report.md"),
        }

    async def emit(self, kind: str, message: str, **detail: Any) -> None:
        payload = {"id": f"event-{time.time_ns()}", "at": time.time(), "kind": kind, "message": message, **detail}
        for queue in list(self.listeners):
            queue.put_nowait(payload)

    async def events(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.listeners.add(queue)
        try:
            yield f"data: {json.dumps({'kind': 'status', 'message': 'Live event stream connected.', 'snapshot': self.snapshot()})}\n\n"
            while True:
                yield f"data: {json.dumps(await queue.get())}\n\n"
        finally:
            self.listeners.discard(queue)

    async def add(self, key: str) -> dict[str, Any]:
        recipe = next((item for item in self.recipes if item.key == key), None)
        if recipe is None:
            raise KeyError(key)
        if recipe.handle in self.workspace.registry.handles():
            await self.emit("notice", f"{recipe.title} is already in the workspace.", participant=recipe.handle)
            return self.snapshot()
        await self.emit("adapter", f"Adapting {recipe.title} through {recipe.uri.split(':', 1)[0]}.", participant=recipe.handle)
        try:
            entry = await self.workspace.add(recipe.uri)
            health = await self.workspace.refresh(entry.handle)
        except Exception as exc:
            await self.emit("failure", f"{recipe.title} could not join: {type(exc).__name__}: {exc}", participant=recipe.handle)
            raise
        affordances = ", ".join(item.name for item in entry.descriptor.affordances)
        await self.emit("participant", f"{recipe.title} joined as {entry.handle}.", participant=entry.handle, affordances=affordances, online=health.online)
        await self.emit("health", f"Liveness probe: {'online' if health.online else 'offline'}{f' — {health.detail}' if health.detail else ''}.", participant=entry.handle)
        return self.snapshot()

    async def quick_load(self) -> dict[str, Any]:
        """Load the prepared non-human recipes without hiding their real probes.

        This is deliberately a demo convenience. It uses exactly the same `Workspace.add`
        and `Workspace.refresh` path as adding each card from the browser.
        """
        failures: list[str] = []
        for recipe in (item for item in self.recipes if item.key != "human"):
            try:
                await self.add(recipe.key)
            except Exception as exc:
                failures.append(f"{recipe.title}: {type(exc).__name__}: {exc}")
        if failures:
            await self.emit("notice", "Quick load finished with prerequisites to fix.", failures=failures)
        else:
            await self.emit("notice", "Quick load complete. Add yourself as the sixth participant when ready.")
        return self.snapshot()

    async def start(self) -> None:
        if self.run_task and not self.run_task.done():
            raise RuntimeError("a case is already running")
        state = self.snapshot()
        if not state["ready"]:
            raise RuntimeError("add and probe every participant before starting the case")
        mnist_test = ROOT / "examples" / "real" / "data" / "MNIST" / "raw" / "t10k-images-idx3-ubyte"
        if not mnist_test.exists():
            raise RuntimeError(
                "the DigitCNN demo data is missing; run `uv run --extra torch python -m examples.real.cnn` once first"
            )
        self.run_task = asyncio.create_task(self._run_case())

    async def _stage(self, title: str, detail: str) -> None:
        await self.emit("stage", title, detail=detail)
        await asyncio.sleep(self.pace)

    async def _call(self, label: str, handle: str, affordance: str, arguments: dict[str, Any]) -> Any:
        assert self.session is not None
        await self.emit("call", f"{label}: {handle}#{affordance}", participant=handle, affordance=affordance, arguments=arguments)
        result: Any = None
        async with aclosing(self.session.call(handle, affordance, arguments)) as stream:
            async for event in stream:
                await self._emit_runtime_event(handle, affordance, event)
                if isinstance(event, Finished):
                    result = event.result
                if isinstance(event, Failed):
                    raise RuntimeError(f"{handle}#{affordance}: {event.code}: {event.message}")
        return result

    async def _emit_runtime_event(self, handle: str, affordance: str, event: Event) -> None:
        data = event.model_dump(mode="json")
        if isinstance(event, Delta) and isinstance(event.part, TextPart):
            message = event.part.text
        elif isinstance(event, ArtifactWritten):
            message = f"Artifact written: {event.ref.name or event.ref.digest}"
        elif isinstance(event, Finished):
            message = f"Finished {handle}#{affordance}"
        elif isinstance(event, Failed):
            message = f"Failed {handle}#{affordance}: {event.message}"
        else:
            message = f"{event.type}: {data.get('message') or data.get('reason') or 'runtime event'}"
        await self.emit("runtime", message, participant=handle, affordance=affordance, event=data)

    async def _run_case(self) -> None:
        self.started_at = time.time()
        await self.emit("run", "LIVE CASE STARTED — Loading-bay evidence review.")
        try:
            async with self.workspace.session(owner="human/reviewer", responder=self._respond) as session:
                self.session = session
                await self._stage("1 / 11 · Establish review intent", "The human joins before any participant is allowed to draw a conclusion.")
                intent = await self._call("ask the human reviewer", "human/reviewer", "choose", {"prompt": "How should this evidence review proceed?", "options": ["Investigate and prepare a report", "Hold the case"]})
                if intent != "Investigate and prepare a report":
                    await self.emit("ended", "The human held the case. No report was prepared.")
                    return

                await self._stage("2 / 11 · Create a real evidence artifact", "DigitCNN receives an artifact reference, not a prompt.")
                image = await self._call("sample MNIST evidence", "local/digits", "sample_digit", {"index": 42})
                await self._stage("3 / 11 · Vision judgement", "The CNN classifies the artifact and reports confidence plus runner-up.")
                vision = await self._call("classify evidence image", "local/digits", "classify", {"image": image})
                await self._stage("4 / 11 · Independent label", "Ground truth is retrieved separately so the verifier has something real to check.")
                truth = await self._call("retrieve independent label", "local/digits", "ground_truth", {"index": 42})

                await self._stage("5 / 11 · Read case context", "The MCP casebook retrieves the provided procedural constraint.")
                notes = await self._call("read case notes", "mcp/casebook", "read_case_notes", {})
                await self._stage("6 / 11 · Render evidence artifact", "The same MCP server produces a chart as an artifact for the shared workspace.")
                await self._call("render confidence chart", "mcp/casebook", "render_evidence_chart", {"title": "Loading-bay digit evidence", "confidence": vision["confidence"]})

                await self._stage("7 / 11 · Symbolic verification", "The verifier compares the CNN observation to the independent label without using language-model judgement.")
                verification = await self._call("verify agreement", "logic/verifier", "rule_verifier", {"observed": vision["digit"], "expected": truth, "confidence": vision["confidence"]})
                await self._stage("8 / 11 · Confidence calibration", "The calibrator turns a raw score plus agreement status into a conservative reporting band.")
                calibration = await self._call("calibrate confidence", "stats/calibrator", "confidence_calibrator", {"confidence": vision["confidence"], "agrees": verification["agrees"]})

                await self._stage("9 / 11 · Gemma synthesises established evidence", "Gemma is constrained to the observed result, verifier decision, calibrated band, and case note.")
                memo = await self._call("draft evidence memo", "openai/cassia", "complete", {"prompt": f"Write a concise factual incident memo using only these facts. CNN digit={vision['digit']}; confidence={vision['confidence']:.1%}; independent label={truth}; verifier={verification['decision']}; calibration={calibration['band']}; case note={notes!r}. Do not invent a cause or a person.", "system": "You are an evidence-bound reporting assistant. State only supplied facts.", "max_tokens": 110})

                await self._stage("10 / 11 · Human review of the draft", "The human chooses whether the evidence is ready to become a persistent report.")
                decision = await self._call("human chooses report posture", "human/reviewer", "choose", {"prompt": "The evidence memo is ready. What should happen?", "options": ["Publish the evidence report", "Hold for more evidence"]})
                if decision != "Publish the evidence report":
                    await self.emit("ended", "The human held the report. The live session ends without a write.")
                    return

                await self._stage("11 / 11 · Approval-gated persistent write", "The MCP server declares this report write; Maiku routes the consequence back to the human.")
                report = "# Loading-bay evidence report\n\n" + str(memo).strip() + "\n\n" + f"Verifier: {verification['decision']}\nCalibration: {calibration['band']}\n"
                await self._call("write approved report", "mcp/casebook", "write_report", {"content": report})
                await self.emit("complete", f"LIVE CASE COMPLETE — report written to {self.case_dir / 'reports' / 'evidence-report.md'}.")
        except Exception as exc:
            await self.emit("failure", f"Live case stopped: {type(exc).__name__}: {exc}")
        finally:
            self.session = None

    async def _browser_answer(self, prompt: str, schema: dict[str, Any]) -> Any:
        options = re.findall(r"^\s*\d+\.\s+(.+)$", prompt, re.MULTILINE)
        clean_prompt = re.split(r"\n\s*1\.\s+", prompt, maxsplit=1)[0]
        return await self._wait_for_human("choose", clean_prompt, {"options": options})

    async def _browser_approve(self, reason: str, detail: dict) -> bool:
        return bool(await self._wait_for_human("approval", reason, {"detail": detail}))

    async def _respond(self, request: NeedsInput | NeedsApproval) -> Any:
        kind = "approval" if isinstance(request, NeedsApproval) else "input"
        prompt = request.reason if isinstance(request, NeedsApproval) else request.prompt
        detail = request.detail if isinstance(request, NeedsApproval) else {"schema": request.input_schema}
        return await self._wait_for_human(kind, prompt, detail, request.request_id)

    async def _wait_for_human(self, kind: str, prompt: str, detail: dict[str, Any], request_id: str | None = None) -> Any:
        request_id = request_id or f"browser-{time.time_ns()}"
        if self.pending:
            raise RuntimeError("another human interaction is already pending")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        request = {"id": request_id, "kind": kind, "prompt": prompt, "detail": detail}
        self.pending_details[request_id] = request
        await self.emit("human_needed", prompt, request=request)
        try:
            return await future
        finally:
            self.pending.pop(request_id, None)
            self.pending_details.pop(request_id, None)

    def _pending_payload(self) -> dict[str, Any] | None:
        if not self.pending:
            return None
        request_id = next(iter(self.pending))
        return self.pending_details[request_id]

    async def respond(self, response: HumanResponse) -> None:
        future = self.pending.get(response.request_id)
        if future is None or future.done():
            raise KeyError(response.request_id)
        future.set_result(response.value)
        await self.emit("human_response", f"Human response received: {response.value!r}.")

    async def close(self) -> None:
        if self.run_task and not self.run_task.done():
            self.run_task.cancel()
            await asyncio.gather(self.run_task, return_exceptions=True)
        self.workspace.close()


def create_app(room: ControlRoom) -> FastAPI:
    app = FastAPI(title="maiku live control room")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return room.snapshot()

    @app.get("/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(room.events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/participants/{key}")
    async def add_participant(key: str) -> dict[str, Any]:
        try:
            return await room.add(key)
        except KeyError as exc:
            raise HTTPException(404, "unknown participant recipe") from exc
        except Exception as exc:
            raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc

    @app.post("/api/quick-load")
    async def quick_load() -> dict[str, Any]:
        return await room.quick_load()

    @app.post("/api/run")
    async def run_case() -> dict[str, Any]:
        try:
            await room.start()
            return room.snapshot()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/human-response")
    async def human_response(response: HumanResponse) -> dict[str, bool]:
        try:
            await room.respond(response)
        except KeyError as exc:
            raise HTTPException(404, "that human request is no longer pending") from exc
        return {"accepted": True}

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await room.close()

    return app


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Maiku live browser control room.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--pace", type=float, default=11.0, help="Seconds between visible case stages; 11 keeps the base trace above two minutes.")
    return parser.parse_args()


if __name__ == "__main__":
    args = arguments()
    if args.pace < 0:
        raise SystemExit("--pace must be non-negative")
    import uvicorn

    uvicorn.run(create_app(ControlRoom(args.pace)), host=args.host, port=args.port, log_level="warning")
