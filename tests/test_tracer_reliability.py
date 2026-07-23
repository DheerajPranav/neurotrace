"""The observer must not break the observed.

Tracer already saved a partial trace when the *traced code* raised. These
tests cover the other half: what happens when the *tracer's own machinery*
(a redact hook, a storage backend) is what fails.
"""

import warnings

import pytest

from neurotrace.adapters.openai import trace_openai
from neurotrace.core.events import EventType
from neurotrace.core.storage import InMemoryStorage, TraceStorage
from neurotrace.core.tracer import Tracer


class FailingStorage(TraceStorage):
    """Always raises on save -- simulates a full disk or a locked file."""

    def save_trace(self, trace):
        raise OSError("disk full")

    def get_trace(self, trace_id):
        return None

    def list_traces(self):
        return []


def test_storage_save_failure_does_not_propagate():
    storage = FailingStorage()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with Tracer(name="agent", storage=storage) as tracer:
            with tracer.llm_call(model="gpt-4o", prompt="hi") as handle:
                handle.response = "ok"
    # Reaching this line at all is the assertion: __exit__ did not raise
    # despite the storage backend failing.


def test_storage_save_failure_emits_a_warning_rather_than_vanishing_silently():
    storage = FailingStorage()

    with pytest.warns(RuntimeWarning, match="disk full"):
        with Tracer(name="agent", storage=storage):
            pass


def test_original_exception_from_traced_code_still_propagates_when_storage_also_fails():
    storage = FailingStorage()

    with pytest.raises(ValueError, match="business logic failed"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with Tracer(name="agent", storage=storage):
                raise ValueError("business logic failed")


def test_redact_hook_failure_does_not_propagate_and_trace_is_simply_unsaved():
    storage = InMemoryStorage()

    def broken_redact(event):
        raise RuntimeError("redact exploded")

    with pytest.warns(RuntimeWarning, match="redact exploded"):
        with Tracer(name="agent", storage=storage, redact=broken_redact) as tracer:
            with tracer.llm_call(model="gpt-4o", prompt="hi") as handle:
                handle.response = "ok"

    # The failure happened before the trace could be persisted -- it's
    # simply not there, not half-written or corrupted.
    assert storage.get_trace(tracer.trace.trace_id) is None


class _Obj:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeRawClient:
    """The minimal shape adapters/openai.py touches: chat.completions.create."""

    def __init__(self):
        self.chat = _Obj(completions=self)

    def create(self, **kwargs):
        message = _Obj(content="hello", tool_calls=None)
        return _Obj(choices=[_Obj(message=message)], usage=None)


def test_wrapping_an_already_traced_client_is_a_no_op():
    tracer = Tracer(name="agent")
    client = trace_openai(FakeRawClient(), tracer)

    rewrapped = trace_openai(client, tracer)

    assert rewrapped is client, "re-wrapping must return the existing proxy, not nest a new one"


def test_accidental_double_wrap_still_records_exactly_one_span_per_call():
    tracer = Tracer(name="agent")
    raw = FakeRawClient()
    once = trace_openai(raw, tracer)
    twice = trace_openai(once, tracer)  # the mistake this guards against

    with tracer:
        twice.chat.completions.create(model="gpt-4o", messages=[])

    assert len(tracer.trace.events) == 1
    assert tracer.trace.events[0].event_type == EventType.LLM_CALL
