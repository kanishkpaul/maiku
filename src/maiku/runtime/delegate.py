"""Letting a model participant call the others.

Every protocol in this space promises agents that delegate; almost none say what a
delegated call costs. Here a tool call from a model goes through the ordinary router path,
so it is grant-checked, approval-gated, traced and recorded in the space exactly like a
call a human made. Delegation is not a side door.

The model does not learn anything maiku-specific: it is handed OpenAI-format tool schemas
projected from the participants it is allowed to use.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from maiku.projections.naming import flatten
from maiku.projections.openai_tools import to_tools
from maiku.runtime.grants import Denied
from maiku.runtime.registry import Entry
from maiku.runtime.session import CallFailed, Session

DEFAULT_TURNS = 6


@dataclass(slots=True)
class Step:
    participant: str
    affordance: str
    arguments: dict[str, Any]
    result: Any = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass(slots=True)
class Delegation:
    answer: str
    steps: list[Step] = field(default_factory=list)
    turns: int = 0
    exhausted: bool = False

    @property
    def delegated(self) -> list[str]:
        return [f"{s.participant}#{s.affordance}" for s in self.steps]


Routes = dict[str, tuple[str, str]]


def toolset(entries: list[Entry], exclude: set[str]) -> tuple[list[dict[str, Any]], Routes]:
    """Tool schemas for the model, and the routing table to turn a call back into a call."""
    tools: list[dict[str, Any]] = []
    routes: Routes = {}

    for entry in entries:
        if entry.handle in exclude:
            continue
        tools.extend(to_tools(entry.descriptor))
        for affordance in entry.descriptor.affordances:
            routes[flatten(entry.handle, affordance.name)] = (entry.handle, affordance.name)
    return tools, routes


async def delegate(
    session: Session,
    model: str,
    goal: str,
    *,
    system: str = "",
    using: list[str] | None = None,
    max_turns: int = DEFAULT_TURNS,
    caller: str | None = None,
    temperature: float = 0.0,
) -> Delegation:
    """Give `model` the other participants as tools and let it work.

    `using` restricts what it may reach. The model is excluded from its own toolset - a
    model offered itself as a tool will eventually call itself.

    A `caller` acting under a narrowed grant must hold the model as well as the tools. That
    is deliberate: the model call is a call, and exempting the delegation mechanism from the
    thing that governs delegation would be the side door this design exists to avoid.
    """
    grant = session.grant_for(caller)
    if not grant.permits(model, "chat"):
        raise Denied(
            f"{caller or 'user'} may not call {model}#chat, so it cannot delegate through it; "
            f"include {model} in the grant"
        )

    everyone = session.participants()
    chosen = [e for e in everyone if using is None or e.handle in using]
    tools, routes = toolset(chosen, exclude={model})

    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": goal})

    outcome = Delegation(answer="")
    for turn in range(1, max_turns + 1):
        outcome.turns = turn
        reply = await session.result(
            model,
            "chat",
            {"messages": messages, "tools": tools, "temperature": temperature},
            caller=caller,
        )
        content, calls = reply.get("content", ""), reply.get("tool_calls") or []

        if not calls:
            outcome.answer = content
            return outcome

        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            step = await _run_tool(session, call, routes, caller)
            outcome.steps.append(step)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or step.affordance,
                    "content": _render(step.error or step.result),
                }
            )

    outcome.exhausted = True
    outcome.answer = content
    return outcome


async def _run_tool(
    session: Session, call: dict[str, Any], routes: Routes, caller: str | None
) -> Step:
    name = (call.get("function") or {}).get("name", "")
    route = routes.get(name)
    if route is None:
        return Step("?", name, {}, error=f"no such tool: {name}")

    handle, affordance = route
    try:
        arguments = json.loads((call.get("function") or {}).get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        return Step(handle, affordance, {}, error=f"arguments were not valid JSON: {exc}")

    step = Step(handle, affordance, arguments)
    try:
        step.result = await session.result(handle, affordance, arguments, caller=caller)
    except CallFailed as failure:
        # Handed back to the model rather than raised: a refused or malformed call is
        # something it can recover from, and hiding it teaches it nothing.
        step.error = f"{failure.event.code}: {failure.event.message}"
    return step


def _render(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)[:4000]
