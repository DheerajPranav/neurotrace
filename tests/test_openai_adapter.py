"""Adapter tests run against a hand-rolled fake client.

The adapter reads response fields structurally rather than importing `openai`,
so these fakes exercise the real code path without the SDK — and the dict-based
test below pins that structural reading in place.
"""

import pytest

from neurotrace.adapters.openai import trace_openai
from neurotrace.core.events import EventType
from neurotrace.core.storage import InMemoryStorage
from neurotrace.core.tracer import Tracer


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message, usage=None):
        self.choices = [FakeChoice(message)]
        self.usage = usage


class FakeCompletions:
    """Returns queued responses in order and records the kwargs it was called with."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, responses):
        self.chat = FakeChat(FakeCompletions(responses))
        self.api_key = "sk-fake"


def test_create_records_llm_call_with_usage_and_passes_through():
    response = FakeResponse(FakeMessage(content="hello"), FakeUsage(11, 4))
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([response]), tracer)

    with tracer:
        returned = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
        )

    assert returned is response, "the caller must get the untouched SDK response back"

    (event,) = tracer.trace.events
    assert event.event_type == EventType.LLM_CALL
    assert event.payload["model"] == "gpt-4o"
    assert event.payload["prompt"] == "user: hi"
    assert event.payload["response"] == "hello"
    assert event.payload["prompt_tokens"] == 11
    assert event.payload["completion_tokens"] == 4
    assert event.duration_ms is not None


def test_dispatch_nests_tool_calls_under_the_completion_that_asked():
    message = FakeMessage(tool_calls=[FakeToolCall("call_1", "search", '{"q": "cats"}')])
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([FakeResponse(message)]), tracer)

    with tracer:
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        results = client.dispatch_tool_calls(response, {"search": lambda q: f"found {q}"})

    assert results == [{"role": "tool", "tool_call_id": "call_1", "content": "found cats"}]

    # Events land in the order their spans *close*, so the completion precedes
    # the tool it requested even though the tool nests under it.
    llm_event, tool_event = tracer.trace.events
    assert tool_event.event_type == EventType.TOOL_CALL
    assert tool_event.payload["tool_name"] == "search"
    assert tool_event.payload["args"] == {"q": "cats"}
    assert tool_event.payload["result"] == "found cats"
    # The tool ran after create() returned, so only explicit re-parenting can
    # put it under the completion rather than beside it.
    assert tool_event.parent_id == llm_event.event_id


def test_unknown_tool_is_recorded_and_fed_back_rather_than_raised():
    message = FakeMessage(tool_calls=[FakeToolCall("call_1", "teleport", "{}")])
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([FakeResponse(message)]), tracer)

    with tracer:
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        results = client.dispatch_tool_calls(response, {"search": lambda q: q})

    assert "no tool named 'teleport'" in results[0]["content"]

    types = [e.event_type for e in tracer.trace.events]
    assert EventType.ERROR in types and EventType.TOOL_CALL in types


def test_malformed_tool_arguments_are_kept_verbatim():
    message = FakeMessage(tool_calls=[FakeToolCall("call_1", "search", "{not json")])
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([FakeResponse(message)]), tracer)

    with tracer:
        response = client.chat.completions.create(model="gpt-4o", messages=[])
        client.dispatch_tool_calls(response, {"search": lambda **kwargs: "ok"})

    tool_event = tracer.trace.events[1]
    assert tool_event.payload["args"] == {"_raw": "{not json"}


def test_tool_execution_error_is_recorded_on_the_span_and_reraised():
    message = FakeMessage(tool_calls=[FakeToolCall("call_1", "search", "{}")])
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([FakeResponse(message)]), tracer)

    def boom():
        raise RuntimeError("tool exploded")

    with pytest.raises(RuntimeError, match="tool exploded"):
        with tracer:
            response = client.chat.completions.create(model="gpt-4o", messages=[])
            client.dispatch_tool_calls(response, {"search": boom})

    tool_event = tracer.trace.events[1]
    assert tool_event.event_type == EventType.TOOL_CALL
    assert tool_event.error == "tool exploded"


def test_api_error_is_recorded_on_the_llm_span_and_reraised():
    tracer = Tracer(name="run")
    storage = InMemoryStorage()
    tracer.storage = storage
    client = trace_openai(FakeClient([RuntimeError("rate limited")]), tracer)

    with pytest.raises(RuntimeError, match="rate limited"):
        with tracer:
            client.chat.completions.create(model="gpt-4o", messages=[])

    saved = storage.get_trace(tracer.trace.trace_id)
    assert saved is not None, "a failed run still has to persist its partial trace"
    assert saved.events[0].error == "rate limited"


def test_dict_responses_work_without_the_sdk_types():
    response = {
        "choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call_1", "function": {"name": "search", "arguments": '{"q": "x"}'}}
        ]}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([response]), tracer)

    with tracer:
        returned = client.chat.completions.create(model="gpt-4o", messages=[])
        results = client.dispatch_tool_calls(returned, {"search": lambda q: f"got {q}"})

    assert results[0]["content"] == "got x"
    llm_event = tracer.trace.events[0]
    assert llm_event.payload["response"] == '[tool_calls] search({"q": "x"})'
    assert llm_event.payload["prompt_tokens"] == 3


def test_uninstrumented_attributes_fall_through_to_the_real_client():
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([]), tracer)

    assert client.api_key == "sk-fake"


def test_multi_turn_loop_nests_each_turn_under_its_own_completion():
    first = FakeResponse(FakeMessage(tool_calls=[FakeToolCall("c1", "search", '{"q": "a"}')]))
    second = FakeResponse(FakeMessage(content="done"))
    tracer = Tracer(name="run")
    client = trace_openai(FakeClient([first, second]), tracer)

    with tracer:
        messages = [{"role": "user", "content": "go"}]
        response = client.chat.completions.create(model="gpt-4o", messages=messages)
        messages += client.dispatch_tool_calls(response, {"search": lambda q: q})
        client.chat.completions.create(model="gpt-4o", messages=messages)

    first_llm, tool_event, second_llm = tracer.trace.events
    assert tool_event.parent_id == first_llm.event_id
    assert second_llm.parent_id is None, "a new turn is a root, not a child of the last one"
