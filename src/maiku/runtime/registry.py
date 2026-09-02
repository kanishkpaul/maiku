"""The local participant registry.

Deliberately a single SQLite file rather than a service. Every previous attempt at a
capability registry died of its own infrastructure; this one has to be cheap enough that
running it is never a decision.

Kept synchronous on purpose: these are microsecond-scale local reads, and wrapping them in
coroutines would buy nothing but noise at every call site.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from maiku.descriptor.enums import Kind
from maiku.descriptor.participant import ParticipantDescriptor
from maiku.wire.health import Health

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    handle      TEXT PRIMARY KEY,
    content_id  TEXT NOT NULL,
    capability_id TEXT NOT NULL DEFAULT '',
    uri         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    descriptor  TEXT NOT NULL,
    health      TEXT,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS participants_kind ON participants(kind);
CREATE INDEX IF NOT EXISTS participants_content ON participants(content_id);
CREATE INDEX IF NOT EXISTS participants_capability ON participants(capability_id);
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


class Registration(BaseModel):
    """What one write did, which `Entry` alone cannot say.

    Kept off `Entry` because it is true of a write rather than of the row: `get`, `list`
    and `find` would all have to invent a value for it.
    """

    model_config = ConfigDict(extra="forbid")

    entry: Entry
    replaced_content_id: str | None = None

    @property
    def is_new(self) -> bool:
        return self.replaced_content_id is None

    @property
    def identity_changed(self) -> bool:
        """The participant now affords something different under a handle already in use.

        The one change worth interrupting an operator for, and the one this registry used
        to overwrite without saying so.
        """
        return not self.is_new and self.replaced_content_id != self.entry.descriptor.id


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
        self._unreadable: dict[str, str] = {}
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        try:
            self._migrate()
            self._db.executescript(SCHEMA)
            self._fts = self._try_fts()
            self._db.commit()
        except Exception:
            self._db.close()
            raise

    @property
    def unreadable(self) -> dict[str, str]:
        return dict(self._unreadable)

    def _migrate(self) -> None:
        """Bring a registry written before capability ids up to the current columns.

        Backfilled from the stored descriptor rather than left empty, so an existing home
        answers `by_capability_id` correctly instead of answering it with silence.
        """
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(participants)")}
        if columns and "capability_id" not in columns:
            self._db.execute(
                "ALTER TABLE participants ADD COLUMN capability_id TEXT NOT NULL DEFAULT ''"
            )
            self._db.commit()

        if not columns:
            return

        sql = (
            "SELECT handle, descriptor FROM participants "
            "WHERE capability_id = '' OR capability_id IS NULL"
        )
        for row in self._db.execute(sql).fetchall():
            handle = row["handle"]
            try:
                descriptor = self._parse_descriptor(handle, row["descriptor"])
                self._db.execute(
                    "UPDATE participants SET capability_id = ? WHERE handle = ?",
                    (descriptor.capability_id, handle),
                )
            except Exception as exc:
                self._unreadable[handle] = str(exc)
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

    def add(self, descriptor: ParticipantDescriptor, uri: str) -> Registration:
        now = time.time()
        previous = self._db.execute(
            "SELECT content_id, first_seen FROM participants WHERE handle = ?",
            (descriptor.handle,),
        ).fetchone()
        first_seen = previous["first_seen"] if previous else now

        self._db.execute(
            """
            INSERT INTO participants
                (handle, content_id, capability_id, uri, kind,
                 descriptor, health, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                content_id    = excluded.content_id,
                capability_id = excluded.capability_id,
                uri        = excluded.uri,
                kind       = excluded.kind,
                descriptor = excluded.descriptor,
                last_seen  = excluded.last_seen
            """,
            (
                descriptor.handle,
                descriptor.id,
                descriptor.capability_id,
                uri,
                descriptor.kind.value,
                descriptor.model_dump_json(),
                first_seen,
                now,
            ),
        )
        self._index(descriptor)
        self._db.commit()
        return Registration(
            entry=Entry(descriptor=descriptor, uri=uri, first_seen=first_seen, last_seen=now),
            replaced_content_id=previous["content_id"] if previous else None,
        )

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
        try:
            return self._entry(row)
        except Exception as exc:
            self._unreadable[handle] = str(exc)
            raise

    def by_content_id(self, content_id: str) -> list[Entry]:
        """Every handle whose descriptor hashes to this id.

        Nothing else in the registry can answer "is this the same thing I already have,
        wearing another name" — a handle lookup only finds the name you already knew.
        """
        rows = self._db.execute(
            "SELECT * FROM participants WHERE content_id = ? ORDER BY handle", (content_id,)
        )
        entries: list[Entry] = []
        for row in rows:
            try:
                entries.append(self._entry(row))
            except Exception as exc:
                self._unreadable[row["handle"]] = str(exc)
        return entries

    def by_capability_id(self, capability_id: str) -> list[Entry]:
        """Every handle affording exactly this, whatever it is called.

        `by_content_id` asks "do I already hold this participant"; this asks "what else is
        the same thing wearing another name" — the question two handles make possible.
        """
        rows = self._db.execute(
            "SELECT * FROM participants WHERE capability_id = ? ORDER BY handle",
            (capability_id,),
        )
        entries: list[Entry] = []
        for row in rows:
            try:
                entries.append(self._entry(row))
            except Exception as exc:
                self._unreadable[row["handle"]] = str(exc)
        return entries

    def list(self, kind: Kind | None = None, online: bool | None = None) -> list[Entry]:
        sql = "SELECT * FROM participants"
        params: list[object] = []
        if kind is not None:
            sql += " WHERE kind = ?"
            params.append(kind.value)
        sql += " ORDER BY handle"

        entries: list[Entry] = []
        for row in self._db.execute(sql, params):
            try:
                entries.append(self._entry(row))
            except Exception as exc:
                self._unreadable[row["handle"]] = str(exc)

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
        entries: list[Entry] = []
        for row in rows:
            try:
                entries.append(self._entry(row))
            except Exception as exc:
                self._unreadable[row["handle"]] = str(exc)
        return entries

    def record_health(self, handle: str, health: Health) -> None:
        self._db.execute(
            "UPDATE participants SET health = ?, last_seen = ? WHERE handle = ?",
            (health.model_dump_json(), time.time(), handle),
        )
        self._db.commit()

    def handles(self) -> list[str]:
        return [row["handle"] for row in self._db.execute("SELECT handle FROM participants")]

    def _parse_descriptor(self, handle: str, descriptor_json: str) -> ParticipantDescriptor:
        try:
            return ParticipantDescriptor.model_validate_json(descriptor_json)
        except ValidationError:
            try:
                data = json.loads(descriptor_json)
                if isinstance(data, dict) and "id" in data:
                    data.pop("id")
                    descriptor = ParticipantDescriptor.model_validate(data)
                    sql = (
                        "UPDATE participants SET content_id = ?, capability_id = ?, "
                        "descriptor = ? WHERE handle = ?"
                    )
                    self._db.execute(
                        sql,
                        (
                            descriptor.id,
                            descriptor.capability_id,
                            descriptor.model_dump_json(),
                            handle,
                        ),
                    )
                    self._db.commit()
                    return descriptor
            except Exception:
                pass
            raise

    def _entry(self, row: sqlite3.Row) -> Entry:
        return Entry(
            descriptor=self._parse_descriptor(row["handle"], row["descriptor"]),
            uri=row["uri"],
            health=Health.model_validate_json(row["health"]) if row["health"] else None,
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


def _fts_query(query: str) -> str:
    """Quote each term so user text cannot be read as FTS5 operator syntax."""
    terms = [t.replace('"', "") for t in query.split() if t.strip()]
    return " OR ".join(f'"{t}"' for t in terms) or '""'
