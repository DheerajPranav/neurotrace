from pathlib import Path

import pytest

from neurotrace.cli import main
from neurotrace.core.events import llm_call_event
from neurotrace.core.storage import SQLiteStorage
from neurotrace.core.tracer import Tracer


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "traces.db"
    storage = SQLiteStorage(db_path)
    with Tracer(name="run-1", storage=storage) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="hi") as call:
            call.response = "hello"
    storage.close()
    return db_path


def test_list_prints_traces(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = _make_db(tmp_path)

    exit_code = main(["list", str(db_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "run-1" in out


def test_list_empty_db_reports_no_traces(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = tmp_path / "empty.db"
    SQLiteStorage(db_path).close()

    exit_code = main(["list", str(db_path)])

    assert exit_code == 0
    assert "(no traces)" in capsys.readouterr().out


def test_view_defaults_to_latest_trace(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = _make_db(tmp_path)

    exit_code = main(["view", str(db_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "run-1" in out
    assert "llm_call" in out


def test_view_with_explicit_trace_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = tmp_path / "traces.db"
    storage = SQLiteStorage(db_path)
    trace_id = "known-id"
    from neurotrace.core.events import Trace

    trace = Trace(trace_id=trace_id, name="named-run")
    trace.add(llm_call_event(trace_id=trace_id, model="gpt-4o", prompt="p", response="r"))
    storage.save_trace(trace)
    storage.close()

    exit_code = main(["view", str(db_path), "--trace-id", trace_id])

    assert exit_code == 0
    assert "named-run" in capsys.readouterr().out


def test_view_unknown_trace_id_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = _make_db(tmp_path)

    exit_code = main(["view", str(db_path), "--trace-id", "nope"])

    assert exit_code == 1
    assert "no trace with id" in capsys.readouterr().err


def test_view_empty_db_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db_path = tmp_path / "empty.db"
    SQLiteStorage(db_path).close()

    exit_code = main(["view", str(db_path)])

    assert exit_code == 1
    assert "no traces in" in capsys.readouterr().err
