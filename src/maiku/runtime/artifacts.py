"""Content-addressed artifact store.

Participants exchange digests, never payloads. That is what keeps a 200 MB video out of
the message log, gives deduplication for free, and — the reason it matters most — makes
"this participant may read that file" a statement the runtime can actually enforce.
"""

import asyncio
import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path

from maiku.wire.parts import ArtifactRef

CHUNK = 1024 * 1024
SHARD = 2


class ArtifactNotFound(KeyError):
    pass


class ArtifactForbidden(PermissionError):
    pass


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._blobs = self.root / "blobs"
        self._meta = self.root / "meta"

    def _blob_path(self, hexdigest: str) -> Path:
        return self._blobs / hexdigest[:SHARD] / hexdigest

    def _meta_path(self, hexdigest: str) -> Path:
        return self._meta / f"{hexdigest}.json"

    @staticmethod
    def _hex(digest: str) -> str:
        return digest.removeprefix("sha256:")

    def exists(self, digest: str) -> bool:
        return self._blob_path(self._hex(digest)).exists()

    async def write(
        self,
        data: bytes | Path,
        media_type: str = "application/octet-stream",
        name: str | None = None,
    ) -> ArtifactRef:
        return await asyncio.to_thread(self._write_sync, data, media_type, name)

    def _write_sync(self, data: bytes | Path, media_type: str, name: str | None) -> ArtifactRef:
        if isinstance(data, bytes):
            hexdigest = hashlib.sha256(data).hexdigest()
            size = len(data)
        else:
            source = Path(data)
            hexdigest = _hash_file(source)
            size = source.stat().st_size
            name = name or source.name

        blob = self._blob_path(hexdigest)
        if not blob.exists():
            blob.parent.mkdir(parents=True, exist_ok=True)
            staging = blob.with_suffix(".partial")
            if isinstance(data, bytes):
                staging.write_bytes(data)
            else:
                shutil.copyfile(data, staging)
            staging.replace(blob)  # atomic, so a reader never sees a half-written blob

        ref = ArtifactRef(
            digest=f"sha256:{hexdigest}",
            media_type=media_type,
            name=name,
            size=size,
        )
        self._meta_path(hexdigest).parent.mkdir(parents=True, exist_ok=True)
        self._meta_path(hexdigest).write_text(ref.model_dump_json())
        return ref

    async def read(self, digest: str) -> bytes:
        return await asyncio.to_thread((await self.path(digest)).read_bytes)

    async def path(self, digest: str) -> Path:
        blob = self._blob_path(self._hex(digest))
        if not blob.exists():
            raise ArtifactNotFound(digest)
        return blob

    async def ref(self, digest: str) -> ArtifactRef:
        meta = self._meta_path(self._hex(digest))
        if not meta.exists():
            raise ArtifactNotFound(digest)
        return ArtifactRef.model_validate_json(meta.read_text())


class ScopedArtifacts:
    """One participant's view of the store.

    Reads are allowlisted per call; writes are always permitted and auto-granted, because a
    participant that cannot read back what it just produced is useless in a pipeline.
    """

    def __init__(
        self,
        store: ArtifactStore,
        readable: set[str] | None = None,
        on_write: Callable[[ArtifactRef], None] | None = None,
    ) -> None:
        self._store = store
        self._readable = set(readable or ())
        self._on_write = on_write

    @property
    def readable(self) -> frozenset[str]:
        return frozenset(self._readable)

    def grant(self, digest: str) -> None:
        self._readable.add(digest)

    def _check(self, digest: str) -> None:
        if digest not in self._readable:
            raise ArtifactForbidden(f"{digest} was not granted to this call")

    async def read(self, digest: str) -> bytes:
        self._check(digest)
        return await self._store.read(digest)

    async def path(self, digest: str) -> Path:
        self._check(digest)
        return await self._store.path(digest)

    async def write(
        self,
        data: bytes | Path,
        media_type: str = "application/octet-stream",
        name: str | None = None,
    ) -> ArtifactRef:
        ref = await self._store.write(data, media_type, name)
        self._readable.add(ref.digest)
        if self._on_write is not None:
            self._on_write(ref)
        return ref
