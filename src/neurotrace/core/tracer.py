"""Tracer: a context manager that wraps one agent run and captures events.

`Tracer` owns a `Trace` for the duration of a `with` block. Nested
`llm_call`/`tool_call` spans time themselves and record duration_ms and
parent_id automatically, so nested calls (e.g. a tool call made while
handling an LLM call's output) render as a tree at read time even though
storage stays flat.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from neurotrace.core.events import (
    Event,
    Trace,
    error_event,
    llm_call_event,
    retry_event,
    tool_call_event,
)
from neurotrace.core.storage import TraceStorage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LLMCallHandle:
    model: str
    prompt: str
    event_id: str
    prompt_tokens: int = 0
    response: str = ""
    completion_tokens: int = 0
    time_to_first_chunk_ms: float | None = None


@dataclass
class ToolCallHandle:
    tool_name: str
    args: dict[str, Any]
    event_id: str
    result: Any = None


class Tracer:
    """One instance per agent run. Use as a context manager; nest
    `llm_call`/`tool_call` spans inside to capture individual decisions."""

    def __init__(
        self,
        name: str,
        storage: TraceStorage | None = None,
        metadata: dict[str, Any] | None = None,
        redact: Callable[[Event], Event] | None = None,
    ) -> None:
        self.trace = Trace(trace_id=str(uuid.uuid4()), name=name, metadata=metadata or {})
        self.storage = storage
        self._redact = redact
        self._parent_stack: list[str | None] = [None]

    def __enter__(self) -> "Tracer":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.trace.ended_at = _utcnow()
        if self.storage is not None:
            trace_to_persist = self.trace
            if self._redact is not None:
                trace_to_persist = replace(
                    self.trace, events=[self._redact(e) for e in self.trace.events]
                )
            self.storage.save_trace(trace_to_persist)
        return False

    @contextmanager
    def under(self, parent_id: str | None) -> Iterator[None]:
        """Attach spans opened inside this block to `parent_id`.

        Lexical nesting covers the common case, but an adapter often learns
        the parent after the fact: an OpenAI response *requests* tool calls
        that only run once `create()` has already returned, so the tool spans
        are siblings of the llm_call span lexically even though they belong
        under it. Pushing the id explicitly re-parents them.
        """
        self._parent_stack.append(parent_id)
        try:
            yield
        finally:
            self._parent_stack.pop()

    @contextmanager
    def llm_call(self, model: str, prompt: str, prompt_tokens: int = 0) -> Iterator[LLMCallHandle]:
        event_id = str(uuid.uuid4())
        handle = LLMCallHandle(
            model=model, prompt=prompt, prompt_tokens=prompt_tokens, event_id=event_id
        )
        parent_id = self._parent_stack[-1]
        self._parent_stack.append(event_id)
        start = time.perf_counter()
        error: str | None = None
        try:
            yield handle
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._parent_stack.pop()
            duration_ms = (time.perf_counter() - start) * 1000
            event = llm_call_event(
                trace_id=self.trace.trace_id,
                model=handle.model,
                prompt=handle.prompt,
                response=handle.response,
                prompt_tokens=handle.prompt_tokens,
                completion_tokens=handle.completion_tokens,
                duration_ms=duration_ms,
                parent_id=parent_id,
                time_to_first_chunk_ms=handle.time_to_first_chunk_ms,
            )
            event.event_id = event_id
            event.error = error
            self.trace.add(event)

    @contextmanager
    def tool_call(self, tool_name: str, args: dict[str, Any]) -> Iterator[ToolCallHandle]:
        event_id = str(uuid.uuid4())
        handle = ToolCallHandle(tool_name=tool_name, args=args, event_id=event_id)
        parent_id = self._parent_stack[-1]
        self._parent_stack.append(event_id)
        start = time.perf_counter()
        error: str | None = None
        try:
            yield handle
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._parent_stack.pop()
            duration_ms = (time.perf_counter() - start) * 1000
            event = tool_call_event(
                trace_id=self.trace.trace_id,
                tool_name=handle.tool_name,
                args=handle.args,
                result=handle.result,
                duration_ms=duration_ms,
                error=error,
                parent_id=parent_id,
            )
            event.event_id = event_id
            self.trace.add(event)

    def retry(self, attempt: int, reason: str) -> None:
        self.trace.add(
            retry_event(
                trace_id=self.trace.trace_id,
                attempt=attempt,
                reason=reason,
                parent_id=self._parent_stack[-1],
            )
        )

    def error(self, message: str) -> None:
        self.trace.add(
            error_event(
                trace_id=self.trace.trace_id,
                message=message,
                parent_id=self._parent_stack[-1],
            )
        )
