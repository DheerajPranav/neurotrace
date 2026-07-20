"""Rebuild the event tree from flat, `parent_id`-linked events.

Day 3 put this logic in `render.py` with the note that a real UI would need
the same step; Day 5's API server is that second consumer, so it moves here
and both callers share one implementation instead of two that drift apart.

`children_by_parent` is the grouping the text renderer walks; `build_tree`
is the nested JSON the HTTP layer serves.
"""

from __future__ import annotations

from typing import Any

from neurotrace.core.events import Event


def children_by_parent(events: list[Event]) -> dict[str | None, list[Event]]:
    """Group events by `parent_id`, treating unresolvable parents as roots.

    An event whose `parent_id` names an event that isn't in the trace would
    otherwise be unreachable from the root walk and vanish from the timeline
    entirely. A trace saved mid-run (or one span-worth of data lost) shouldn't
    silently drop the remaining spans, so orphans re-attach at the top level
    where they stay visible — losing their nesting is a much smaller lie than
    losing the event.
    """
    known = {event.event_id for event in events}
    children: dict[str | None, list[Event]] = {}
    for event in events:
        parent_id = event.parent_id if event.parent_id in known else None
        children.setdefault(parent_id, []).append(event)
    return children


def build_tree(events: list[Event]) -> list[dict[str, Any]]:
    """Nest events into `Event.to_dict()` payloads carrying a `children` list.

    Shaped for a consumer that renders the tree directly (Day 6's timeline),
    so the nesting is resolved here rather than left as `parent_id` pointers
    for client-side code to re-derive.
    """
    children = children_by_parent(events)

    def walk(parent_id: str | None) -> list[dict[str, Any]]:
        nodes = []
        for event in children.get(parent_id, []):
            node = event.to_dict()
            node["children"] = walk(event.event_id)
            nodes.append(node)
        return nodes

    return walk(None)
