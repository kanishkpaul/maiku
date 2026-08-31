"""The local participant registry.

Deliberately a single SQLite file rather than a service. Every previous attempt at a
capability registry died of its own infrastructure; this one has to be cheap enough that
running it is never a decision.

Kept synchronous on purpose: these are microsecond-scale local reads, and wrapping them in
coroutines would buy nothing but noise at every call site.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from maiku.descriptor.enums import Kind
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.wire.health import Health

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    handle      TEXT PRIMARY KEY,
    content_id  TEXT NOT NULL,
    uri         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    descriptor  TEXT NOT NULL,
    health      TEXT,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS participants_kind ON participants(kind);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS participant_search
USING fts5(handle UNINDEXED, body);
"""


class UnknownParticipant(KeyError):
    pass


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ParticipantDescriptor
    uri: str
    health: Health | None = None
    first_seen: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)

    @property
    def handle(self) -> str:
        return self.descriptor.handle

    @property
    def online(self) -> bool:
        return bool(self.health and self.health.online)


def searchable_text(descriptor: ParticipantDescriptor) -> str:
    """What `maiku find` matches against.

    Summaries and example notes are included because capability matching from type
    signatures alone has never worked; the prose is the signal.
    """
    parts = [
        descriptor.handle,
        descriptor.display.name,
        descriptor.display.description,
        *descriptor.display.tags,
        descriptor.kind.value,
    ]
    for affordance in descriptor.affordances:
        parts += [affordance.name, affordance.summary, affordance.description]
        parts += affordance.tags
        parts += [e.note for e in affordance.examples if e.note]
    return " ".join(p for p in parts if p)


class Registry:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._fts = self._try_fts()
        self._db.commit()

    def _try_fts(self) -> bool:
        try:
            self._db.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError:
            return False  # FTS5 is usually present; LIKE is a survivable fallback
        return True

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Registry:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def add(self, descriptor: ParticipantDescriptor, uri: str) -> Entry:
        now = time.time()
        existing = self._db.execute(
            "SELECT first_seen FROM participants WHERE handle = ?", (descriptor.handle,)
        ).fetchone()
        first_seen = existing["first_seen"] if existing else now

        self._db.execute(
            """
            INSERT INTO participants
                (handle, content_id, uri, kind, descriptor, health, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                content_id = excluded.content_id,
                uri        = excluded.uri,
                kind       = excluded.kind,
                descriptor = excluded.descriptor,
                last_seen  = excluded.last_seen
            """,
            (
                descriptor.handle,
                descriptor.id,
                uri,
                descriptor.kind.value,
                descriptor.model_dump_json(),
                first_seen,
                now,
            ),
        )
        self._index(descriptor)
        self._db.commit()
        return Entry(descriptor=descriptor, uri=uri, first_seen=first_seen, last_seen=now)

    def _index(self, descriptor: ParticipantDescriptor) -> None:
        if not self._fts:
            return
        self._db.execute("DELETE FROM participant_search WHERE handle = ?", (descriptor.handle,))
        self._db.execute(
            "INSERT INTO participant_search (handle, body) VALUES (?, ?)",
            (descriptor.handle, searchable_text(descriptor)),
        )

    def remove(self, handle: str) -> bool:
        cursor = self._db.execute("DELETE FROM participants WHERE handle = ?", (handle,))
        if self._fts:
            self._db.execute("DELETE FROM participant_search WHERE handle = ?", (handle,))
        self._db.commit()
        return cursor.rowcount > 0

    def get(self, handle: str) -> Entry:
        row = self._db.execute("SELECT * FROM participants WHERE handle = ?", (handle,)).fetchone()
        if row is None:
            raise UnknownParticipant(handle)
        return self._entry(row)

    def list(self, kind: Kind | None = None, online: bool | None = None) -> list[Entry]:
        sql = "SELECT * FROM participants"
        params: list[object] = []
        if kind is not None:
            sql += " WHERE kind = ?"
            params.append(kind.value)
        sql += " ORDER BY handle"

        entries = [self._entry(row) for row in self._db.execute(sql, params)]
        if online is None:
            return entries
        return [e for e in entries if e.online is online]

    def find(self, query: str, limit: int = 20) -> list[Entry]:
        if self._fts:
            rows = self._db.execute(
                """
                SELECT p.* FROM participant_search s
                JOIN participants p ON p.handle = s.handle
                WHERE participant_search MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (_fts_query(query), limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM participants WHERE descriptor LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [self._entry(row) for row in rows]

    def record_health(self, handle: str, health: Health) -> None:
        self._db.execute(
            "UPDATE participants SET health = ?, last_seen = ? WHERE handle = ?",
            (health.model_dump_json(), time.time(), handle),
        )
        self._db.commit()

    def handles(self) -> list[str]:
        return [row["handle"] for row in self._db.execute("SELECT handle FROM participants")]

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            descriptor=ParticipantDescriptor.model_validate_json(row["descriptor"]),
            uri=row["uri"],
            health=Health.model_validate_json(row["health"]) if row["health"] else None,
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


def _fts_query(query: str) -> str:
    """Quote each term so user text cannot be read as FTS5 operator syntax."""
    terms = [t.replace('"', "") for t in query.split() if t.strip()]
    return " OR ".join(f'"{t}"' for t in terms) or '""'


def bulk_add(registry: Registry, pairs: Iterable[tuple[ParticipantDescriptor, str]]) -> int:
    return sum(1 for descriptor, uri in pairs if registry.add(descriptor, uri))
