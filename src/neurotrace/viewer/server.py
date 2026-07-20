"""Read-only JSON API over a trace database.

`create_app(db_path)` serves the traces in one SQLite file: summaries for a
list view, one trace flat as stored, and one trace nested as rendered. Day 6's
timeline UI is the intended consumer — this is the seam between "we have the
data" and "you can look at it," and it exists as its own layer so the UI is a
static asset talking HTTP rather than Python generating markup.

Nothing here mutates a trace. The API is a viewer for runs that already
happened; writes belong to `Tracer`, in the process being traced.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException

from neurotrace.core.storage import SQLiteStorage
from neurotrace.viewer.render import render_trace
from neurotrace.viewer.tree import build_tree

# Loopback, not 0.0.0.0. A trace holds prompts, tool arguments, and tool
# results verbatim (see README "Data handling"), so the default has to be a
# server nobody else on the network can read. Binding wider is a decision the
# operator makes explicitly, with `--host`.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8756


def create_app(db_path: str | Path) -> FastAPI:
    """Build a FastAPI app serving the traces in `db_path`.

    Raises `FileNotFoundError` if the database doesn't exist: `SQLiteStorage`
    creates its schema on connect, so a typo'd path would otherwise produce a
    brand-new empty database and an API that cheerfully reports zero traces.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"no trace database at {path}")

    app = FastAPI(
        title="NeuroTrace",
        description="Read-only API over a NeuroTrace trace database.",
    )

    @contextmanager
    def storage() -> Iterator[SQLiteStorage]:
        """A connection per request, closed when the request ends.

        Not a shared instance: FastAPI runs sync endpoints in a worker
        threadpool, and sqlite3 rejects a connection used from a thread other
        than the one that created it. Opening per request is microseconds
        against a local file and keeps the server free of shared mutable
        state — which is also why the tracer's own single-connection design
        isn't reused here.
        """
        conn = SQLiteStorage(path)
        try:
            yield conn
        finally:
            conn.close()

    def _load(trace_id: str) -> Any:
        with storage() as conn:
            trace = conn.get_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail=f"no trace with id {trace_id!r}")
        return trace

    @app.get("/api/traces")
    def list_traces() -> list[dict[str, Any]]:
        """Every trace in the database, without its events."""
        with storage() as conn:
            return [summary.to_dict() for summary in conn.list_trace_summaries()]

    @app.get("/api/traces/{trace_id}")
    def get_trace(trace_id: str) -> dict[str, Any]:
        """One trace with its events as stored — a flat, parent_id-linked list."""
        return _load(trace_id).to_dict()

    @app.get("/api/traces/{trace_id}/tree")
    def get_trace_tree(trace_id: str) -> dict[str, Any]:
        """One trace with its events nested into the shape a timeline draws.

        The same `parent_id` resolution the text renderer does, served as JSON
        so the UI renders a tree instead of re-deriving one.
        """
        trace = _load(trace_id)
        payload = trace.to_dict()
        payload["events"] = build_tree(trace.events)
        return payload

    @app.get("/api/traces/{trace_id}/text")
    def get_trace_text(trace_id: str) -> dict[str, Any]:
        """The terminal timeline, as text. Lets a client show the same view
        `neurotrace view` prints without reimplementing the renderer."""
        return {"trace_id": trace_id, "text": render_trace(_load(trace_id))}

    return app
