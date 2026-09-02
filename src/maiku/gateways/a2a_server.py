"""Serve maiku participants as A2A agents.

The mirror of the MCP gateway. Together they mean a participant adapted from any source can
be consumed through either protocol, and the source is invisible to the consumer.

The awkward seam is real and worth naming: A2A senders speak in messages, while a maiku
affordance has a typed schema. `arguments_from` resolves that explicitly rather than
pretending every participant takes a string.
"""

import json
from typing import Any

from maiku.descriptor.affordance import Affordance
from maiku.projections.a2a import PROTOCOL_VERSION, to_agent_card
from maiku.projections.naming import handle_slug
from maiku.projections.visible import visible
from maiku.runtime.grants import Grant
from maiku.runtime.registry import Entry
from maiku.runtime.session import Session
from maiku.wire.events import ArtifactWritten, Failed, Finished
from maiku.wire.task import TaskState

WELL_KNOWN = "/.well-known/agent-card.json"
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

A2A_STATES = {
    TaskState.COMPLETED: "completed",
    TaskState.FAILED: "failed",
    TaskState.CANCELED: "canceled",
    TaskState.REJECTED: "rejected",
    TaskState.WORKING: "working",
    TaskState.SUBMITTED: "submitted",
    TaskState.INPUT_REQUIRED: "input-required",
    TaskState.AUTH_REQUIRED: "auth-required",
    TaskState.APPROVAL_REQUIRED: "input-required",
}


def text_of(parts: list[dict[str, Any]]) -> str:
    return "".join(p.get("text", "") for p in parts if p.get("kind", "text") == "text")


def arguments_from(message: dict[str, Any], affordance: Affordance) -> dict[str, Any]:
    """Get typed arguments out of an A2A message.

    Three routes, in order of how explicit the sender was being: a data part is taken as the
    arguments outright; text that parses as a JSON object is treated the same way; otherwise
    the text fills the affordance's single required string, which is the common case for
    agent-shaped participants.
    """
    for part in message.get("parts") or []:
        if part.get("kind") == "data" and isinstance(part.get("data"), dict):
            return part["data"]

    text = text_of(message.get("parts") or [])
    try:
        if isinstance(parsed := json.loads(text), dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    schema = affordance.input_schema
    required = schema.get("required") or list(schema.get("properties") or {})
    strings = [
        name
        for name in required
        if (schema.get("properties") or {}).get(name, {}).get("type") in {None, "string"}
    ]
    return {strings[0]: text} if strings else {"message": text}


class A2AGateway:
    """Serves one connected client, under that client's grant.

    Like the MCP gateway: no grant means no skills and no routes, not the whole workspace.
    """

    def __init__(
        self,
        session: Session,
        base_url: str = "http://localhost:8080",
        *,
        grant: Grant | None = None,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.grant = grant

    def _visible(self, entry: Entry) -> list[Affordance]:
        return visible(entry.descriptor, self.grant) if self.grant else []

    def _entry(self, slug: str) -> Entry | None:
        for entry in self.session.participants():
            if handle_slug(entry.handle) == slug:
                return entry
        return None

    def agent_card(self, slug: str | None = None) -> dict[str, Any] | None:
        if slug is None:
            return self._aggregate_card()
        entry = self._entry(slug)
        if entry is None:
            return None
        if self.grant is None:
            return None
        return to_agent_card(
            entry.descriptor, self.grant, base_url=f"{self.base_url}/agents/{slug}"
        )

    def _aggregate_card(self) -> dict[str, Any]:
        """One card for the whole workspace, each participant's affordances as skills."""
        skills = []
        for entry in self.session.participants():
            slug = handle_slug(entry.handle)
            for affordance in self._visible(entry):
                skills.append(
                    {
                        "id": f"{slug}__{affordance.name}",
                        "name": f"{entry.descriptor.display.name}: {affordance.summary}",
                        "description": affordance.description or affordance.summary,
                        "tags": [entry.descriptor.kind.value, *affordance.tags],
                        "examples": [e.note for e in affordance.examples if e.note],
                        "inputModes": entry.descriptor.io_defaults.input_modes,
                        "outputModes": entry.descriptor.io_defaults.output_modes,
                    }
                )

        return {
            "protocolVersion": PROTOCOL_VERSION,
            "name": "maiku",
            "description": "Everything adapted in this workspace, as one agent",
            "url": self.base_url,
            "preferredTransport": "JSONRPC",
            "version": "0.0.1",
            "provider": {"organization": "maiku", "url": self.base_url},
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "stateTransitionHistory": True,
            },
            "defaultInputModes": ["text/plain", "application/json"],
            "defaultOutputModes": ["text/plain", "application/json"],
            "skills": skills,
            "supportsAuthenticatedExtendedCard": False,
        }

    def _resolve(self, skill: str, slug: str | None) -> tuple[str, str] | None:
        """Only what this client can see resolves, so an unoffered skill has no route."""
        if slug is not None:
            entry = self._entry(slug)
            name = skill
        else:
            participant_slug, sep, name = skill.rpartition("__")
            if not sep:
                return None
            entry = self._entry(participant_slug)

        if entry is None or name not in {a.name for a in self._visible(entry)}:
            return None
        return entry.handle, name

    async def rpc(self, message: dict[str, Any], slug: str | None = None) -> dict[str, Any] | None:
        message_id = message.get("id")
        if message_id is None:
            return None
        try:
            result = await self._dispatch(message.get("method"), message.get("params") or {}, slug)
        except LookupError as exc:
            return _error(message_id, METHOD_NOT_FOUND, str(exc))
        except ValueError as exc:
            return _error(message_id, INVALID_PARAMS, str(exc))
        except Exception as exc:
            return _error(message_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    async def _dispatch(self, method: str | None, params: dict, slug: str | None) -> Any:
        if method == "message/send":
            return await self._send(params, slug)
        if method == "tasks/get":
            return self._task_view(params.get("id", ""))
        if method == "tasks/cancel":
            task_id = params.get("id", "")
            if not self.session.router.cancel(task_id):
                raise ValueError(f"no cancellable task {task_id!r}")
            return self._task_view(task_id)
        raise LookupError(f"no such method: {method}")

    async def _send(self, params: dict, slug: str | None) -> dict[str, Any]:
        message = params.get("message") or {}
        skill = (message.get("metadata") or {}).get("maiku/skill") or params.get("skill")
        if not skill:
            raise ValueError("no skill named; set message.metadata['maiku/skill']")

        route = self._resolve(skill, slug)
        if route is None:
            raise ValueError(f"no participant serving skill {skill!r}")
        handle, affordance_name = route

        entry = self.session.workspace.registry.get(handle)
        try:
            affordance = entry.descriptor.affordance(affordance_name)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        arguments = arguments_from(message, affordance)
        artifacts: list[dict[str, Any]] = []
        result: Any = None
        state = TaskState.COMPLETED
        detail = ""
        task_id = ""

        async for event in self.session.call(
            handle, affordance_name, arguments, caller=self.grant.subject, grant=self.grant
        ):
            task_id = task_id or self._latest_task_id(handle)
            if isinstance(event, ArtifactWritten):
                artifacts.append(
                    {
                        "artifactId": event.ref.digest,
                        "name": event.ref.name or "artifact",
                        "parts": [
                            {
                                "kind": "file",
                                "file": {
                                    "uri": f"maiku://artifact/{event.ref.digest}",
                                    "mimeType": event.ref.media_type,
                                    "name": event.ref.name,
                                },
                            }
                        ],
                    }
                )
            elif isinstance(event, Finished):
                result, state = event.result, event.state
            elif isinstance(event, Failed):
                state, detail = TaskState.FAILED, f"{event.code}: {event.message}"

        if result is not None:
            artifacts.insert(
                0,
                {
                    "artifactId": f"{task_id}-result",
                    "name": "result",
                    "parts": [{"kind": "text", "text": _render(result)}],
                },
            )

        return {
            "kind": "task",
            "id": task_id,
            "contextId": self.session.id,
            "status": {"state": A2A_STATES[state], "message": _status_message(detail)},
            "artifacts": artifacts,
        }

    def _latest_task_id(self, handle: str) -> str:
        for task in reversed(list(self.session.router.tasks.values())):
            if task.participant == handle:
                return task.id
        return ""

    def _task_view(self, task_id: str) -> dict[str, Any]:
        task = self.session.router.tasks.get(task_id)
        if task is None:
            raise ValueError(f"no task {task_id!r}")
        return {
            "kind": "task",
            "id": task.id,
            "contextId": self.session.id,
            "status": {
                "state": A2A_STATES[task.status.state],
                "message": _status_message(task.status.detail),
            },
            "artifacts": [
                {"artifactId": digest, "name": "artifact", "parts": []}
                for digest in task.metadata.get("artifacts", [])
            ],
        }


def _status_message(detail: str) -> dict[str, Any] | None:
    if not detail:
        return None
    return {"role": "agent", "parts": [{"kind": "text", "text": detail}]}


def _render(result: Any) -> str:
    return result if isinstance(result, str) else json.dumps(result, default=str)


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
