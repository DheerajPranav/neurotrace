from pathlib import Path

from neurotrace.core.events import Trace, llm_call_event, tool_call_event
from neurotrace.core.storage import InMemoryStorage, SQLiteStorage


def _sample_trace() -> Trace:
    trace = Trace(trace_id="t1", name="demo")
    trace.add(llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r"))
    trace.add(tool_call_event(trace_id="t1", tool_name="search", args={"q": "x"}, result="ok"))
    return trace


def test_in_memory_storage_roundtrip():
    storage = InMemoryStorage()
    storage.save_trace(_sample_trace())

    fetched = storage.get_trace("t1")
    assert fetched is not None
    assert fetched.trace_id == "t1"
    assert len(fetched.events) == 2


def test_in_memory_storage_missing_trace_returns_none():
    storage = InMemoryStorage()
    assert storage.get_trace("nope") is None


def test_sqlite_storage_roundtrip(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "traces.db")
    storage.save_trace(_sample_trace())

    fetched = storage.get_trace("t1")
    assert fetched is not None
    assert len(fetched.events) == 2
    assert fetched.events[0].payload["model"] == "gpt-4o"
    storage.close()


def test_sqlite_storage_list_traces(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "traces.db")
    storage.save_trace(_sample_trace())

    traces = storage.list_traces()
    assert len(traces) == 1
    assert traces[0].trace_id == "t1"
    storage.close()


def test_sqlite_storage_persists_across_reopen(tmp_path: Path):
    db_path = tmp_path / "traces.db"
    storage = SQLiteStorage(db_path)
    storage.save_trace(_sample_trace())
    storage.close()

    reopened = SQLiteStorage(db_path)
    fetched = reopened.get_trace("t1")
    assert fetched is not None
    assert len(fetched.events) == 2
    reopened.close()


def test_sqlite_storage_save_trace_twice_upserts_not_duplicates(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "traces.db")
    trace = _sample_trace()
    storage.save_trace(trace)
    storage.save_trace(trace)

    fetched = storage.get_trace("t1")
    assert fetched is not None
    assert len(fetched.events) == 2
    storage.close()
