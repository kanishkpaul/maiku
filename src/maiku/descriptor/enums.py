"""Closed vocabularies of the descriptor.

These stay small on purpose. Every value a participant may declare is one another
participant has to reason about, and an open vocabulary is a vocabulary nobody agrees on.
"""

from enum import StrEnum


class Kind(StrEnum):
    """What sort of thing a participant fundamentally is."""

    MODEL = "model"
    AGENT = "agent"
    TOOL = "tool"
    SERVICE = "service"
    HUMAN = "human"
    ROBOT = "robot"
    NOTEBOOK = "notebook"
    PIPELINE = "pipeline"


class AffordanceKind(StrEnum):
    """The four interaction shapes, borrowed from W3C Web of Things.

    Every system we have tried to adapt reduces to these: a classifier invokes, an LLM
    streams, a robot joint is a property, a monitor emits events.
    """

    INVOKE = "invoke"
    STREAM = "stream"
    PROPERTY = "property"
    EVENT = "event"


class AffordanceOperation(StrEnum):
    """The operation a call performs within an interaction shape.

    A property read and property write cannot share an authorization decision: one only
    observes state while the other changes the world. Keeping the operation explicit lets
    each appear as its own caller-relative affordance with its own schema and side effect.
    """

    INVOKE = "invoke"
    READ = "read"
    WRITE = "write"
    SUBSCRIBE = "subscribe"


class Determinism(StrEnum):
    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"
    SIDE_EFFECTING = "side_effecting"


class LatencyClass(StrEnum):
    """Order-of-magnitude response time.

    `HUMAN` is what lets a person sit in the same participant list as a GPU without the
    runtime needing a special case for people.
    """

    INSTANT = "instant"
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    HUMAN = "human"


class SideEffect(StrEnum):
    """Worst-case consequence of a call, ordered by escalating blast radius."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"


class Residency(StrEnum):
    """Where the computation physically happens."""

    IN_PROCESS = "in_process"
    SUBPROCESS = "subprocess"
    LOCAL_SERVICE = "local_service"
    REMOTE = "remote"
    HUMAN = "human"


class Device(StrEnum):
    NONE = "none"
    CPU = "cpu"
    MPS = "mps"
    CUDA = "cuda"
    ROCM = "rocm"
    TPU = "tpu"


class Transport(StrEnum):
    IN_PROCESS = "in_process"
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    WEBSOCKET = "websocket"
    GRPC = "grpc"
    JSONRPC = "jsonrpc"
    SUBPROCESS = "subprocess"
    TTY = "tty"


class Approval(StrEnum):
    """When a human must sign off before a call proceeds."""

    NEVER = "never"
    ON_SCOPE = "on_scope"
    ALWAYS = "always"


class ProbeKind(StrEnum):
    NONE = "none"
    ADAPTER = "adapter"
    HTTP = "http"
    TCP = "tcp"
    PROCESS = "process"


SIDE_EFFECT_ORDER: dict[SideEffect, int] = {
    SideEffect.NONE: 0,
    SideEffect.READ: 1,
    SideEffect.WRITE: 2,
    SideEffect.EXTERNAL: 3,
    SideEffect.IRREVERSIBLE: 4,
}


def max_side_effect(effects: "list[SideEffect]") -> SideEffect:
    return max(effects, key=lambda e: SIDE_EFFECT_ORDER[e], default=SideEffect.NONE)
