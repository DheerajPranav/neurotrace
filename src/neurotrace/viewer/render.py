"""Text rendering of a Trace as an indented timeline.

Day 3 scope is a terminal renderer, not the full timeline UI promised by
`viewer/` eventually — it's the fastest way to make `neurotrace view` useful
today, and the tree-building logic (parent_id -> children) is the same logic
a future HTML/JS viewer will need, so it's factored out here rather than
inlined in the CLI.
"""

from __future__ import annotations

from neurotrace.core.events import Event, Trace

_BRANCH = "├─ "
_LAST_BRANCH = "└─ "
_PIPE = "│  "
_BLANK = "   "


def _summarize(event: Event) -> str:
    parts = [event.event_type.value]

    if event.event_type.value == "llm_call":
        parts.append(event.payload.get("model", ""))
    elif event.event_type.value == "tool_call":
        parts.append(event.payload.get("tool_name", ""))
    elif event.event_type.value == "retry":
        parts.append(f"attempt={event.payload.get('attempt')} {event.payload.get('reason', '')}")

    if event.duration_ms is not None:
        parts.append(f"{event.duration_ms:.1f}ms")

    summary = "  ".join(p for p in parts if p)
    if event.error:
        summary += f"  [error: {event.error}]"
    return summary


def _build_children(events: list[Event]) -> dict[str | None, list[Event]]:
    children: dict[str | None, list[Event]] = {}
    for event in events:
        children.setdefault(event.parent_id, []).append(event)
    return children


def _render_children(
    children: dict[str | None, list[Event]],
    parent_id: str | None,
    prefix: str,
    lines: list[str],
) -> None:
    siblings = children.get(parent_id, [])
    for i, event in enumerate(siblings):
        is_last = i == len(siblings) - 1
        branch = _LAST_BRANCH if is_last else _BRANCH
        lines.append(f"{prefix}{branch}{_summarize(event)}")
        next_prefix = prefix + (_BLANK if is_last else _PIPE)
        _render_children(children, event.event_id, next_prefix, lines)


def render_trace(trace: Trace) -> str:
    """Render a Trace as an indented timeline, ordered by nesting (parent_id)
    rather than raw event order."""
    ended = trace.ended_at.isoformat() if trace.ended_at else "(in progress)"
    header = f"Trace: {trace.name}  ({trace.trace_id})  {trace.started_at.isoformat()} -> {ended}"

    if not trace.events:
        return header + "\n  (no events)"

    children = _build_children(trace.events)
    lines: list[str] = []
    _render_children(children, None, "", lines)
    return header + "\n" + "\n".join(lines)
