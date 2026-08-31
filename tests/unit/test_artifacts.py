import pytest

from maiku.adapters.context import ArtifactIO
from maiku.runtime.artifacts import (
    ArtifactForbidden,
    ArtifactNotFound,
    ArtifactStore,
    ScopedArtifacts,
)


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "artifacts")


async def test_write_is_content_addressed(store):
    a = await store.write(b"hello", media_type="text/plain", name="a.txt")
    b = await store.write(b"hello", media_type="text/plain", name="b.txt")
    assert a.digest == b.digest
    assert a.size == 5


async def test_read_round_trips(store):
    ref = await store.write(b"payload")
    assert await store.read(ref.digest) == b"payload"


async def test_large_file_is_hashed_by_streaming(store, tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(b"x" * (3 * 1024 * 1024))
    ref = await store.write(source, media_type="application/octet-stream")
    assert ref.size == 3 * 1024 * 1024
    assert ref.name == "big.bin"
    assert store.exists(ref.digest)


async def test_missing_digest_raises(store):
    with pytest.raises(ArtifactNotFound):
        await store.read("sha256:" + "0" * 64)


async def test_metadata_survives(store):
    ref = await store.write(b"{}", media_type="application/json", name="x.json")
    assert (await store.ref(ref.digest)).media_type == "application/json"


async def test_scoped_view_blocks_ungranted_reads(store):
    ref = await store.write(b"secret")
    scoped = ScopedArtifacts(store)
    with pytest.raises(ArtifactForbidden):
        await scoped.read(ref.digest)

    scoped.grant(ref.digest)
    assert await scoped.read(ref.digest) == b"secret"


async def test_writes_are_self_granted_and_announced(store):
    seen = []
    scoped = ScopedArtifacts(store, on_write=seen.append)
    ref = await scoped.write(b"produced", media_type="text/plain")
    assert await scoped.read(ref.digest) == b"produced"
    assert [r.digest for r in seen] == [ref.digest]


def test_scoped_view_satisfies_the_adapter_protocol(store):
    assert isinstance(ScopedArtifacts(store), ArtifactIO)
