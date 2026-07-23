"""Event schema for agent execution traces.

Design: one flat Event dataclass with a `payload` dict, rather than a class
per event kind (LLMCallEvent, ToolCallEvent, ...). Rationale is in
docs/architecture.md — short version: a flat schema serializes to
SQLite/JSON without per-type tables or (de)serialization branching, and
adapters (LangChain, OpenAI, ...) rarely agree on field names, so a rigid
subclass hierarchy would just get punned into a dict anyway.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    DECISION = "decision"
    ERROR = "error"
    RETRY = "retry"


@dataclass
class Event:
    trace_id: str
    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    duration_ms: float | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            event_id=data["event_id"],
            trace_id=data["trace_id"],
            event_type=EventType(data["event_type"]),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data.get("duration_ms"),
            parent_id=data.get("parent_id"),
            error=data.get("error"),
        )


def llm_call_event(
    trace_id: str,
    model: str,
    prompt: str,
    response: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: float | None = None,
    parent_id: str | None = None,
    time_to_first_chunk_ms: float | None = None,
) -> Event:
    return Event(
        trace_id=trace_id,
        event_type=EventType.LLM_CALL,
        payload={
            "model": model,
            "prompt": prompt,
            "response": response,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            # None for a non-streamed call -- there is no meaningful
            # "first chunk" when the whole response arrives at once.
            "time_to_first_chunk_ms": time_to_first_chunk_ms,
        },
        duration_ms=duration_ms,
        parent_id=parent_id,
    )


def tool_call_event(
    trace_id: str,
    tool_name: str,
    args: dict[str, Any],
    result: Any = None,
    duration_ms: float | None = None,
    error: str | None = None,
    parent_id: str | None = None,
) -> Event:
    return Event(
        trace_id=trace_id,
        event_type=EventType.TOOL_CALL,
        payload={"tool_name": tool_name, "args": args, "result": result},
        duration_ms=duration_ms,
        error=error,
        parent_id=parent_id,
    )


def error_event(
    trace_id: str,
    message: str,
    parent_id: str | None = None,
) -> Event:
    return Event(
        trace_id=trace_id,
        event_type=EventType.ERROR,
        error=message,
        parent_id=parent_id,
    )


def retry_event(
    trace_id: str,
    attempt: int,
    reason: str,
    parent_id: str | None = None,
) -> Event:
    return Event(
        trace_id=trace_id,
        event_type=EventType.RETRY,
        payload={"attempt": attempt, "reason": reason},
        parent_id=parent_id,
    )


@dataclass
class Trace:
    trace_id: str
    name: str
    started_at: datetime = field(default_factory=_utcnow)
    ended_at: datetime | None = None
    events: list[Event] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, event: Event) -> None:
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "metadata": self.metadata,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        return cls(
            trace_id=data["trace_id"],
            name=data["name"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            metadata=data.get("metadata", {}),
            events=[Event.from_dict(e) for e in data.get("events", [])],
        )
