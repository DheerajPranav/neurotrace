from neurotrace.core.events import llm_call_event, tool_call_event
from neurotrace.viewer.tree import build_tree, children_by_parent


def test_build_tree_nests_children_under_their_parent():
    parent = llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r")
    child = tool_call_event(
        trace_id="t1", tool_name="search", args={}, result="ok", parent_id=parent.event_id
    )

    (root,) = build_tree([parent, child])

    assert root["event_id"] == parent.event_id
    (nested,) = root["children"]
    assert nested["event_id"] == child.event_id
    assert nested["children"] == []


def test_build_tree_handles_events_appended_before_their_parent():
    """Spans append when they close, so a child can precede its parent in the
    stored list. Tree shape must come from parent_id, not list order."""
    parent = llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r")
    child = tool_call_event(trace_id="t1", tool_name="search", args={}, parent_id=parent.event_id)

    (root,) = build_tree([child, parent])

    assert root["event_id"] == parent.event_id
    assert [c["event_id"] for c in root["children"]] == [child.event_id]


def test_orphaned_events_surface_as_roots_rather_than_vanishing():
    orphan = tool_call_event(trace_id="t1", tool_name="search", args={}, parent_id="missing-id")

    roots = build_tree([orphan])

    assert [node["event_id"] for node in roots] == [orphan.event_id]


def test_children_by_parent_groups_siblings_in_order():
    parent = llm_call_event(trace_id="t1", model="gpt-4o", prompt="p", response="r")
    first = tool_call_event(trace_id="t1", tool_name="a", args={}, parent_id=parent.event_id)
    second = tool_call_event(trace_id="t1", tool_name="b", args={}, parent_id=parent.event_id)

    grouped = children_by_parent([parent, first, second])

    assert grouped[None] == [parent]
    assert grouped[parent.event_id] == [first, second]
