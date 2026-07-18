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

## Day 2 — Tracer + storage

**Tracer owns one Trace per run.** `Tracer(name, storage=None)` is used
as a context manager bounding one agent run; `llm_call`/`tool_call` are
nested context managers within it that yield a mutable handle (e.g.
`call.response = ...`), time themselves, and build the actual `Event` on
exit via the Day 1 constructor functions. `__exit__` always sets
`ended_at` and persists to storage if given — even on an uncaught
exception, so a partial trace isn't lost.

**Parent tracking without a tree structure at capture time:** a stack of
`event_id`s on the Tracer. Entering a span pushes a pre-generated
`event_id` (so children can reference it as `parent_id` before the span
itself has finished and built its `Event`); exiting pops it. This is why
the constructor functions build the `Event` first and then have
`event_id` overwritten — the id has to exist before the span's own event
does, so nested children can address it.

**Errors are recorded on the span they occurred in, not the whole run:**
if a call inside `llm_call`/`tool_call` raises, that span's `Event.error`
is set and the exception re-raises through `Tracer.__exit__` unmodified.
Considered also emitting a run-level `error_event` from
`Tracer.__exit__` on any uncaught exception, but that double-counts
whatever span already recorded it, and an exception raised *between*
spans (not inside one) is an edge case not worth an error path for — the
trace still ends and saves normally either way.

**Storage: one interface, two backends.** `TraceStorage` (ABC) with
`InMemoryStorage` (dict, for tests) and `SQLiteStorage` (the two-table
schema sketched below, upsert-based so re-saving an in-progress trace
updates rather than duplicates rows).

```
traces(trace_id PK, name, started_at, ended_at, metadata_json)
events(event_id PK, trace_id, event_type, payload_json, timestamp,
       duration_ms, parent_id, error)  -- indexed on trace_id
```

## Day 3 — CLI + text-based trace rendering

**`neurotrace list|view <db_path>`.** `cli.py` opens a `SQLiteStorage`
and either lists trace summaries or renders one trace. `view` defaults
to the most recently *started* trace (`list_traces()` is already
ordered by `started_at`, so that's just the last element) when no
`--trace-id` is given — the common case right after a run is "show me
what just happened," not looking up an id first.

**Rendering lives in `viewer/`, not `cli.py`.** `viewer/render.py`
turns a `Trace`'s flat, `parent_id`-linked event list into an indented
tree at read time — this is the "inferred at render time" step Day 1's
schema note deferred. `render_trace` returns a plain string (no I/O)
so `cli.py` just prints it and tests can assert on content directly.
This split matters because the tree-building (`parent_id` -> children,
depth-first walk) is exactly what a future HTML/JS timeline view will
also need; keeping it out of the CLI means that viewer can reuse it
instead of re-deriving the tree from scratch.

**Errors are stderr + exit code 1, not exceptions.** Unknown
`--trace-id` or an empty db are expected user-facing conditions (typo'd
id, wrong path), not bugs — `_cmd_view`/`_cmd_list` return an int status
and print to `sys.stderr` rather than letting a `KeyError` or similar
surface as a traceback.

## Next (Day 4)

An adapter (`adapters/`) that instruments a real framework (OpenAI
function-calling first, probably) instead of requiring manual
`tracer.llm_call(...)` calls. The full HTML/JS timeline viewer (`viewer/`
has only the text renderer so far) is the other open piece, but the
adapter is more valuable next — right now every example still has to
call the Tracer API by hand.
