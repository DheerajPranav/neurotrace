"""Trace storage backends.

Two implementations behind one interface: `InMemoryStorage` for tests,
`SQLiteStorage` for the on-disk traces `neurotrace view` will read back
later. Schema is the one sketched in docs/architecture.md — a `traces`
table plus an `events` table indexed on trace_id.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from neurotrace.core.events import Event, EventType, Trace


class TraceStorage(ABC):
    @abstractmethod
    def save_trace(self, trace: Trace) -> None: ...

    @abstractmethod
    def get_trace(self, trace_id: str) -> Trace | None: ...

    @abstractmethod
    def list_traces(self) -> list[Trace]: ...


class InMemoryStorage(TraceStorage):
    def __init__(self) -> None:
        self._traces: dict[str, Trace] = {}

    def save_trace(self, trace: Trace) -> None:
        self._traces[trace.trace_id] = Trace.from_dict(trace.to_dict())

    def get_trace(self, trace_id: str) -> Trace | None:
        return self._traces.get(trace_id)

    def list_traces(self) -> list[Trace]:
        return list(self._traces.values())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES traces(trace_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration_ms REAL,
    parent_id TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id);
"""


class SQLiteStorage(TraceStorage):
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_trace(self, trace: Trace) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO traces (trace_id, name, started_at, ended_at, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    name = excluded.name,
                    ended_at = excluded.ended_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    trace.trace_id,
                    trace.name,
                    trace.started_at.isoformat(),
                    trace.ended_at.isoformat() if trace.ended_at else None,
                    json.dumps(trace.metadata),
                ),
            )
            for event in trace.events:
                self._conn.execute(
                    """
                    INSERT INTO events
                        (event_id, trace_id, event_type, payload_json, timestamp, duration_ms, parent_id, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        duration_ms = excluded.duration_ms,
                        error = excluded.error
                    """,
                    (
                        event.event_id,
                        event.trace_id,
                        event.event_type.value,
                        json.dumps(event.payload),
                        event.timestamp.isoformat(),
                        event.duration_ms,
                        event.parent_id,
                        event.error,
                    ),
                )

    def get_trace(self, trace_id: str) -> Trace | None:
        row = self._conn.execute(
            "SELECT trace_id, name, started_at, ended_at, metadata_json FROM traces WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return None

        trace = Trace(
            trace_id=row[0],
            name=row[1],
            started_at=datetime.fromisoformat(row[2]),
            ended_at=datetime.fromisoformat(row[3]) if row[3] else None,
            metadata=json.loads(row[4]),
        )
        event_rows = self._conn.execute(
            """
            SELECT event_id, trace_id, event_type, payload_json, timestamp, duration_ms, parent_id, error
            FROM events WHERE trace_id = ? ORDER BY timestamp
            """,
            (trace_id,),
        ).fetchall()
        for r in event_rows:
            trace.events.append(
                Event(
                    event_id=r[0],
                    trace_id=r[1],
                    event_type=EventType(r[2]),
                    payload=json.loads(r[3]),
                    timestamp=datetime.fromisoformat(r[4]),
                    duration_ms=r[5],
                    parent_id=r[6],
                    error=r[7],
                )
            )
        return trace

    def list_traces(self) -> list[Trace]:
        rows = self._conn.execute("SELECT trace_id FROM traces ORDER BY started_at").fetchall()
        traces = []
        for (trace_id,) in rows:
            trace = self.get_trace(trace_id)
            if trace is not None:
                traces.append(trace)
        return traces

    def close(self) -> None:
        self._conn.close()
