import pytest

from neurotrace.core.events import EventType
from neurotrace.core.storage import InMemoryStorage
from neurotrace.core.tracer import Tracer


def test_tracer_captures_llm_call_and_persists():
    storage = InMemoryStorage()
    with Tracer(name="run", storage=storage) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="hi") as call:
            call.response = "hello"
            call.completion_tokens = 3

    saved = storage.get_trace(tracer.trace.trace_id)
    assert saved is not None
    assert len(saved.events) == 1
    event = saved.events[0]
    assert event.event_type == EventType.LLM_CALL
    assert event.payload["response"] == "hello"
    assert event.payload["completion_tokens"] == 3
    assert event.duration_ms is not None and event.duration_ms >= 0
    assert saved.ended_at is not None


def test_tracer_tool_call_records_error_and_reraises():
    tracer = Tracer(name="run")
    with pytest.raises(RuntimeError):
        with tracer:
            with tracer.tool_call(tool_name="search", args={"q": "x"}):
                raise RuntimeError("boom")

    assert len(tracer.trace.events) == 1
    event = tracer.trace.events[0]
    assert event.event_type == EventType.TOOL_CALL
    assert event.error == "boom"


def test_nested_calls_track_parent_id():
    tracer = Tracer(name="run")
    with tracer:
        with tracer.llm_call(model="gpt-4o", prompt="hi") as outer:
            outer.response = "plan"
            with tracer.tool_call(tool_name="search", args={}) as inner:
                inner.result = "ok"

    inner_event, outer_event = tracer.trace.events
    assert inner_event.event_type == EventType.TOOL_CALL
    assert outer_event.event_type == EventType.LLM_CALL
    assert inner_event.parent_id == outer_event.event_id
    assert outer_event.parent_id is None


def test_tracer_saves_partial_trace_on_exception():
    storage = InMemoryStorage()
    with pytest.raises(ValueError):
        with Tracer(name="run", storage=storage) as tracer:
            with tracer.llm_call(model="gpt-4o", prompt="hi") as call:
                call.response = "partial"
            raise ValueError("bad run")

    saved = storage.get_trace(tracer.trace.trace_id)
    assert saved is not None
    assert saved.ended_at is not None
    assert len(saved.events) == 1


def test_retry_and_error_helpers_record_events():
    tracer = Tracer(name="run")
    with tracer:
        tracer.retry(attempt=1, reason="rate_limited")
        tracer.error("gave up")

    assert len(tracer.trace.events) == 2
    assert tracer.trace.events[0].event_type == EventType.RETRY
    assert tracer.trace.events[1].event_type == EventType.ERROR
    assert tracer.trace.events[1].error == "gave up"
