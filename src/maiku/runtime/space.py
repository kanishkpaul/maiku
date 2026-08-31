"""The shared space participants talk in.

A threaded, mention-addressed log rather than point-to-point channels. The blackboard
shape is what lets a participant that was not part of the original plan notice relevant
work and join in - and it means adding a fifth participant does not require rewiring the
other four.

Payloads are parts; anything large travels as an artifact reference.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maiku.wire.parts import Part, TextPart
from maiku.wire.task import new_id

EVERYONE = "*"


class Post(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("post"))
    thread_id: str
    author: str
    mentions: list[str] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    task_id: str | None = None
    at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))

    def addressed_to(self, handle: str) -> bool:
        return not self.mentions or handle in self.mentions or EVERYONE in self.mentions


class Subscription:
    def __init__(self, space: "Space", mentions: str | None) -> None:
        self._space = space
        self._mentions = mentions
        self._queue: asyncio.Queue[Post] = asyncio.Queue()
        self._closed = False

    def _offer(self, post: Post) -> None:
        if self._closed:
            return
        if self._mentions is None or post.addressed_to(self._mentions):
            self._queue.put_nowait(post)

    async def __aiter__(self) -> AsyncIterator[Post]:
        while not self._closed:
            yield await self._queue.get()

    async def next(self, timeout: float | None = None) -> Post:
        return await asyncio.wait_for(self._queue.get(), timeout)

    def close(self) -> None:
        self._closed = True
        self._space._unsubscribe(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class Space:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._posts: list[Post] = []
        self._subscribers: list[Subscription] = []

    def post(
        self,
        author: str,
        parts: Iterable[Part] | str,
        *,
        mentions: Iterable[str] = (),
        thread_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Post:
        if isinstance(parts, str):
            parts = [TextPart(text=parts)]

        post = Post(
            thread_id=thread_id or new_id("thread"),
            author=author,
            mentions=list(mentions),
            parts=list(parts),
            task_id=task_id,
            metadata=metadata or {},
        )
        self._posts.append(post)
        for subscriber in list(self._subscribers):
            subscriber._offer(post)
        return post

    def history(
        self,
        *,
        thread_id: str | None = None,
        addressed_to: str | None = None,
        author: str | None = None,
        after: float | None = None,
    ) -> list[Post]:
        posts = self._posts
        if thread_id is not None:
            posts = [p for p in posts if p.thread_id == thread_id]
        if addressed_to is not None:
            posts = [p for p in posts if p.addressed_to(addressed_to)]
        if author is not None:
            posts = [p for p in posts if p.author == author]
        if after is not None:
            posts = [p for p in posts if p.at > after]
        return list(posts)

    def threads(self) -> list[str]:
        return list(dict.fromkeys(p.thread_id for p in self._posts))

    def subscribe(self, mentions: str | None = None) -> Subscription:
        subscription = Subscription(self, mentions)
        self._subscribers.append(subscription)
        return subscription

    def _unsubscribe(self, subscription: Subscription) -> None:
        if subscription in self._subscribers:
            self._subscribers.remove(subscription)

    def __len__(self) -> int:
        return len(self._posts)
