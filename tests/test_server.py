from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neurotrace.core.events import Trace, tool_call_event
from neurotrace.core.storage import SQLiteStorage
from neurotrace.core.tracer import Tracer
from neurotrace.viewer.server import _UI_FILE, create_app


def _make_db(tmp_path: Path) -> Path:
    """A db holding one run: an llm_call with a tool_call nested under it."""
    db_path = tmp_path / "traces.db"
    storage = SQLiteStorage(db_path)
    with Tracer(name="run-1", storage=storage, metadata={"provider": "scripted"}) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="hi") as call:
            call.response = "hello"
            with tracer.tool_call(tool_name="search", args={"q": "x"}) as tool:
                tool.result = "ok"
    storage.close()
    return db_path


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(_make_db(tmp_path)))


def test_create_app_rejects_missing_database(tmp_path: Path):
    # SQLiteStorage would happily create one, leaving the API reporting an
    # empty db instead of the typo the user actually made.
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "nope.db")


def test_list_traces_returns_summaries_without_events(client: TestClient):
    response = client.get("/api/traces")

    assert response.status_code == 200
    (summary,) = response.json()
    assert summary["name"] == "run-1"
    assert summary["event_count"] == 2
    assert summary["error_count"] == 0
    assert summary["metadata"] == {"provider": "scripted"}
    assert "events" not in summary


def test_list_traces_counts_errors(tmp_path: Path):
    db_path = tmp_path / "traces.db"
    storage = SQLiteStorage(db_path)
    trace = Trace(trace_id="t1", name="failing-run")
    trace.add(tool_call_event(trace_id="t1", tool_name="boom", args={}, error="no tool"))
    storage.save_trace(trace)
    storage.close()

    (summary,) = TestClient(create_app(db_path)).get("/api/traces").json()

    assert summary["error_count"] == 1


def test_get_trace_returns_flat_events(client: TestClient):
    trace_id = client.get("/api/traces").json()[0]["trace_id"]

    body = client.get(f"/api/traces/{trace_id}").json()

    assert body["name"] == "run-1"
    assert len(body["events"]) == 2
    # Flat as stored: nesting is still only a parent_id pointer here.
    assert all("children" not in event for event in body["events"])
    assert any(event["parent_id"] is not None for event in body["events"])


def test_get_trace_tree_nests_events(client: TestClient):
    trace_id = client.get("/api/traces").json()[0]["trace_id"]

    body = client.get(f"/api/traces/{trace_id}/tree").json()

    (root,) = body["events"]
    assert root["event_type"] == "llm_call"
    (child,) = root["children"]
    assert child["event_type"] == "tool_call"
    assert child["payload"]["tool_name"] == "search"
    assert child["children"] == []


def test_get_trace_text_matches_the_cli_renderer(client: TestClient):
    trace_id = client.get("/api/traces").json()[0]["trace_id"]

    text = client.get(f"/api/traces/{trace_id}/text").json()["text"]

    assert "run-1" in text
    assert "llm_call" in text
    assert "search" in text


@pytest.mark.parametrize("suffix", ["", "/tree", "/text"])
def test_unknown_trace_id_is_404(client: TestClient, suffix: str):
    response = client.get(f"/api/traces/nope{suffix}")

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_empty_database_lists_nothing(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    SQLiteStorage(db_path).close()

    response = TestClient(create_app(db_path)).get("/api/traces")

    assert response.status_code == 200
    assert response.json() == []


def test_requests_survive_the_worker_threadpool(client: TestClient):
    """Sync endpoints run in a threadpool, and sqlite3 refuses a connection
    used off its creating thread — so a shared connection would raise here on
    a later request even though the first one passed."""
    for _ in range(5):
        assert client.get("/api/traces").status_code == 200


def test_api_is_read_only(client: TestClient):
    trace_id = client.get("/api/traces").json()[0]["trace_id"]

    assert client.post("/api/traces", json={}).status_code == 405
    assert client.delete(f"/api/traces/{trace_id}").status_code == 405


def test_serves_the_viewer_ui(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "NeuroTrace" in body
    assert 'id="trace-list"' in body  # the mount point the JS fills in


def test_ui_asset_is_packaged():
    # Shipped alongside the module so a wheel install serves the page too,
    # not only a source checkout.
    assert _UI_FILE.exists()


def test_ui_makes_no_external_requests(client: TestClient):
    """The page must stay self-contained: a trace holds prompts and tool
    results verbatim, so a viewer that pulled a script or font off a CDN would
    leak exactly the data this tool keeps local. Encoded as a test so a stray
    external reference can't slip in later."""
    body = client.get("/").text

    # No element loads a resource from off-machine: no absolute or
    # protocol-relative src/href, and no @import pulling in a remote sheet.
    for needle in ('src="http', "src='http", 'src="//', 'href="http', 'href="//', "@import url(http"):
        assert needle not in body
