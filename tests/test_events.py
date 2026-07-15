from neurotrace.core.events import (
    Event,
    EventType,
    Trace,
    llm_call_event,
    tool_call_event,
    error_event,
    retry_event,
)


def test_llm_call_event_roundtrip():
    e = llm_call_event(
        trace_id="t1",
        model="gpt-4o",
        prompt="hi",
        response="hello",
        prompt_tokens=1,
        completion_tokens=1,
        duration_ms=120.5,
    )
    assert e.event_type == EventType.LLM_CALL
    restored = Event.from_dict(e.to_dict())
    assert restored.payload["model"] == "gpt-4o"
    assert restored.duration_ms == 120.5


def test_tool_call_event_carries_error():
    e = tool_call_event(
        trace_id="t1",
        tool_name="search",
        args={"query": "x"},
        error="timeout",
    )
    assert e.error == "timeout"
    assert e.payload["tool_name"] == "search"


def test_retry_and_error_events():
    r = retry_event(trace_id="t1", attempt=2, reason="rate_limited")
    assert r.payload["attempt"] == 2
    err = error_event(trace_id="t1", message="boom")
    assert err.error == "boom"


def test_trace_accumulates_events_and_roundtrips():
    trace = Trace(trace_id="t1", name="demo")
    trace.add(llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r"))
    trace.add(tool_call_event(trace_id="t1", tool_name="search", args={}))
    assert len(trace.events) == 2

    restored = Trace.from_dict(trace.to_dict())
    assert restored.trace_id == "t1"
    assert len(restored.events) == 2
    assert restored.events[0].event_type == EventType.LLM_CALL


def test_event_ids_are_unique():
    e1 = error_event(trace_id="t1", message="a")
    e2 = error_event(trace_id="t1", message="b")
    assert e1.event_id != e2.event_id
