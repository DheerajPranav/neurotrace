from neurotrace.core.events import Trace, llm_call_event, tool_call_event
from neurotrace.viewer.render import render_trace


def test_render_empty_trace_shows_header_and_placeholder():
    trace = Trace(trace_id="t1", name="demo")
    output = render_trace(trace)
    assert "demo" in output
    assert "t1" in output
    assert "(no events)" in output


def test_render_nests_children_under_parent():
    trace = Trace(trace_id="t1", name="demo")
    outer = llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r", duration_ms=10.0)
    trace.add(outer)
    inner = tool_call_event(
        trace_id="t1", tool_name="search", args={}, result="ok", duration_ms=5.0, parent_id=outer.event_id
    )
    trace.add(inner)

    output = render_trace(trace)
    lines = output.splitlines()

    outer_line = next(line for line in lines if "gpt-4o" in line)
    inner_line = next(line for line in lines if "search" in line)
    assert lines.index(inner_line) > lines.index(outer_line)
    assert inner_line.startswith("   ") or inner_line.startswith("│") or inner_line.startswith(" ")
    assert "10.0ms" in outer_line
    assert "5.0ms" in inner_line


def test_render_shows_error_marker():
    trace = Trace(trace_id="t1", name="demo")
    event = tool_call_event(trace_id="t1", tool_name="search", args={}, error="boom")
    trace.add(event)

    output = render_trace(trace)
    assert "[error: boom]" in output
