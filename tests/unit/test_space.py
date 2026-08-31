import asyncio

import pytest

from maiku.runtime.space import Space
from maiku.wire.parts import TextPart


@pytest.fixture
def space():
    return Space("s_test")


def test_post_and_read_back(space):
    post = space.post("local/llm", "hello")
    assert post.text == "hello"
    assert space.history() == [post]


def test_threading(space):
    first = space.post("a/one", "start")
    space.post("a/two", "reply", thread_id=first.thread_id)
    space.post("a/one", "elsewhere")
    assert len(space.history(thread_id=first.thread_id)) == 2
    assert len(space.threads()) == 2


def test_mentions_address_specific_participants(space):
    broadcast = space.post("a/one", "anyone?")
    direct = space.post("a/one", "you", mentions=["a/two"])

    assert broadcast.addressed_to("a/three")
    assert not direct.addressed_to("a/three")
    assert [p.id for p in space.history(addressed_to="a/two")] == [broadcast.id, direct.id]


def test_filters_compose(space):
    space.post("a/one", "x")
    space.post("a/two", "y")
    assert [p.author for p in space.history(author="a/two")] == ["a/two"]


async def test_subscription_receives_matching_posts(space):
    with space.subscribe("a/two") as sub:
        space.post("a/one", "for you", mentions=["a/two"])
        space.post("a/one", "for someone else", mentions=["a/three"])
        received = await sub.next(timeout=1)
        assert received.text == "for you"
        with pytest.raises(TimeoutError):
            await sub.next(timeout=0.05)


async def test_closing_a_subscription_detaches_it(space):
    sub = space.subscribe()
    sub.close()
    space.post("a/one", "after close")
    assert space._subscribers == []


def test_parts_pass_through(space):
    post = space.post("a/one", [TextPart(text="a"), TextPart(text="b")])
    assert post.text == "ab"


async def test_many_subscribers_all_see_a_post(space):
    subs = [space.subscribe() for _ in range(3)]
    space.post("a/one", "broadcast")
    texts = await asyncio.gather(*(s.next(timeout=1) for s in subs))
    assert [t.text for t in texts] == ["broadcast"] * 3
