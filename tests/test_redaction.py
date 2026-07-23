from neurotrace.core.events import llm_call_event, tool_call_event
from neurotrace.core.storage import InMemoryStorage
from neurotrace.core.tracer import Tracer
from neurotrace.redaction import redact_secrets


def test_redact_secrets_masks_openai_style_key_in_payload():
    event = llm_call_event(
        trace_id="t1",
        model="gpt-4o",
        prompt="my key is sk-abcdefghijklmnopqrstuvwxyz123456",
        response="ok",
    )

    redacted = redact_secrets(event)

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in redacted.payload["prompt"]
    assert "[REDACTED]" in redacted.payload["prompt"]


def test_redact_secrets_masks_bearer_token():
    event = llm_call_event(
        trace_id="t1",
        model="gpt-4o",
        prompt="Authorization: Bearer abc123.def456-ghi",
        response="ok",
    )

    redacted = redact_secrets(event)

    assert "abc123.def456-ghi" not in redacted.payload["prompt"]


def test_redact_secrets_walks_nested_tool_args():
    event = tool_call_event(
        trace_id="t1",
        tool_name="call_api",
        args={"headers": {"api_key": "supersecretvalue123"}, "safe": "keep me"},
        result="fine",
    )

    redacted = redact_secrets(event)

    assert "supersecretvalue123" not in str(redacted.payload["args"])
    assert redacted.payload["args"]["safe"] == "keep me"


def test_redact_secrets_leaves_ordinary_content_unchanged():
    event = llm_call_event(
        trace_id="t1", model="gpt-4o", prompt="what's the weather", response="sunny"
    )

    redacted = redact_secrets(event)

    assert redacted.payload["prompt"] == "what's the weather"
    assert redacted.payload["response"] == "sunny"


def test_redact_secrets_masks_error_message():
    event = tool_call_event(
        trace_id="t1",
        tool_name="call_api",
        args={},
        error="auth failed for Bearer topsecrettoken123",
    )

    redacted = redact_secrets(event)

    assert "topsecrettoken123" not in redacted.error


def test_tracer_with_no_redact_hook_stores_verbatim():
    storage = InMemoryStorage()

    with Tracer(name="agent", storage=storage) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="sk-abcdefghijklmnopqrstuvwxyz123456") as h:
            h.response = "ok"

    saved = storage.get_trace(tracer.trace.trace_id)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" in saved.events[0].payload["prompt"]


def test_tracer_with_redact_hook_stores_redacted_copy():
    storage = InMemoryStorage()

    with Tracer(name="agent", storage=storage, redact=redact_secrets) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="sk-abcdefghijklmnopqrstuvwxyz123456") as h:
            h.response = "ok"

    saved = storage.get_trace(tracer.trace.trace_id)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in saved.events[0].payload["prompt"]


def test_redact_hook_does_not_mutate_in_process_trace():
    storage = InMemoryStorage()

    with Tracer(name="agent", storage=storage, redact=redact_secrets) as tracer:
        with tracer.llm_call(model="gpt-4o", prompt="sk-abcdefghijklmnopqrstuvwxyz123456") as h:
            h.response = "ok"

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" in tracer.trace.events[0].payload["prompt"]


def test_redact_hook_applies_on_partial_trace_saved_after_exception():
    storage = InMemoryStorage()

    try:
        with Tracer(name="agent", storage=storage, redact=redact_secrets) as tracer:
            with tracer.tool_call(tool_name="lookup", args={"key": "sk-abcdefghijklmnopqrstuvwxyz123456"}):
                raise RuntimeError("boom")
    except RuntimeError:
        pass

    saved = storage.get_trace(tracer.trace.trace_id)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(saved.events[0].payload)
