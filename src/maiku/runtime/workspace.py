"""Durable local state: what has been adapted, and the files it produced.

A workspace outlives any session. Sessions are cheap and disposable; the registry and the
artifact store are the parts worth keeping.
"""

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maiku.adapters.registry import open_participant
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.runtime.artifacts import ArtifactStore
from maiku.runtime.home import home
from maiku.runtime.registry import Registration, Registry
from maiku.wire.health import Health

if TYPE_CHECKING:
    from maiku.runtime.session import Session


class Workspace:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else home()
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = Registry(self.root / "registry.sqlite")
        self.artifacts = ArtifactStore(self.root / "artifacts")

    async def add(self, uri: str, handle: str | None = None) -> Registration:
        """Adapt something and remember it.

        The adapter is closed again straight after describing: registration should not pin
        a model into memory, and the router reopens lazily on first call.
        """
        adapter = await open_participant(uri)
        try:
            descriptor = await adapter.describe()
        finally:
            with contextlib.suppress(Exception):
                await adapter.close()

        if handle is not None:
            descriptor = ParticipantDescriptor(
                **(descriptor.model_dump(mode="json", exclude={"id"}) | {"handle": handle})
            )
        return self.registry.add(descriptor, uri)

    async def refresh(self, handle: str) -> Health:
        entry = self.registry.get(handle)
        adapter = await open_participant(entry.uri)
        try:
            health = await adapter.probe()
        except Exception as exc:
            health = Health.down(f"{type(exc).__name__}: {exc}")
        finally:
            with contextlib.suppress(Exception):
                await adapter.close()

        self.registry.record_health(handle, health)
        return health

    def session(self, **kwargs: Any) -> "Session":
        from maiku.runtime.session import Session

        return Session(self, **kwargs)

    def close(self) -> None:
        self.registry.close()

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
