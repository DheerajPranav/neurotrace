# Architecture notes

## Day 1 — Event schema

**Decision:** one flat `Event` dataclass (`event_type` + `payload: dict`)
instead of a class hierarchy (`LLMCallEvent`, `ToolCallEvent`, ...).

**Why:** the schema has to survive two things a class hierarchy fights
against — serialization to SQLite/JSON, and adapters that each shape
their data differently (LangChain's callback payloads look nothing like
raw OpenAI function-calling payloads). A flat schema means one table,
one `to_dict`/`from_dict`, and adapters just build whatever payload dict
makes sense for them. The cost is weaker type safety on `payload` — an
LLM event and a tool event are both just "an Event with a dict." Free-form
constructor functions (`llm_call_event`, `tool_call_event`, ...) recover
some of that safety at the call site without needing subclasses.

**Trace vs Event:** `Trace` is the container (one per agent run), holds
an ordered list of `Event`s plus start/end time and metadata. `parent_id`
on `Event` exists so retries/errors can reference the call they belong
to, without forcing a rigid tree structure yet — that can be inferred at
render time in the viewer rather than enforced at capture time.

## Next (Day 2)

Tracer needs to be usable as a context manager around a function call,
and storage needs both an in-memory path (for tests) and SQLite (for
`neurotrace view` reading a trace back later). Sketching: one `traces`
table (trace_id, name, started_at, ended_at, metadata_json) and one
`events` table (event_id, trace_id, event_type, payload_json, timestamp,
duration_ms, parent_id, error), indexed on trace_id.
