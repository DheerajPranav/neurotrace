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

## Day 4 — OpenAI adapter

**`trace_openai(client, tracer)` returns a proxy, not a patch.** The
alternative was monkeypatching `openai.resources.chat.Completions.create`
globally. A proxy loses the ability to trace a client the user constructed
somewhere you can't reach, but it's explicit about what's traced, nests
correctly when two tracers are alive at once, and doesn't break when the
SDK reorganizes its internals. `__getattr__` delegates everything
uninstrumented to the real client, so the proxy is a drop-in and the
agent loop in `examples/openai_agent.py` contains no NeuroTrace calls at
all — only the construction line changes.

**The `openai` package is never imported.** Response fields are read
structurally through `_get`, which handles both mappings and attribute
objects. This keeps `openai` out of `pyproject.toml` for a library whose
job is observing agents rather than calling them, and it means the same
adapter accepts pydantic SDK models, `model_dump()` dicts, recorded
fixtures, and OpenAI-compatible clients from other vendors. The tests
run against hand-written fakes with no SDK installed, which is also the
honest way to test this — a mock of the SDK's types would be asserting
against our own guesses either way.

**`Tracer.under(parent_id)` exists because of an ordering mismatch.**
Day 2's parent tracking is lexical: a span is a child of whatever span
encloses it. But an OpenAI response *requests* tool calls that only run
after `create()` has already returned and closed its span, so the tool
calls are lexical siblings of the completion that caused them. The
adapter records each completion's `event_id` (now exposed on the span
handle) and re-parents the dispatched tools under it. Without this the
timeline is a flat alternating list of llm/tool spans with the causal
link — *this* call asked for *that* tool — thrown away, which is most of
what makes the tree worth rendering. Note this makes event list order
(spans append on close) differ from tree order; the renderer already
walks by `parent_id`, so it doesn't care.

**Hallucinated tool vs. broken tool are handled differently, on purpose.**
A tool call naming a tool that doesn't exist records an errored span and
returns the error to the model as the tool's result, letting the loop
continue. A tool that raises while executing propagates unmodified.
The asymmetry is that the first is agent behaviour NeuroTrace exists to
show you — it belongs in the trace, not in a traceback — while the second
is ordinary application code failing, and swallowing it would hide a real
bug behind a trace entry. Same reasoning for `_parse_arguments` keeping
malformed JSON under `_raw` instead of raising: unparseable tool arguments
are a symptom to capture, and a decode error would destroy the evidence.

## Day 4a — tool-call validation (security follow-up)

Review before making the repo public turned up two problems with
`fn(**args)`, both from splatting model-controlled JSON straight into a
Python callable.

**The tool schema is a security boundary, so it's now enforced.** A
parameter that exists on the Python function was model-settable even when
the schema never offered it — a `read_file(path, allow_absolute=False)`
whose schema declares only `path` could be called with
`allow_absolute=True` by a prompt-injected tool call. Arguments are now
restricted to the properties the schema declares. The schemas don't need
a new parameter: they were already passed to `create(tools=...)`, so the
proxy records them and `dispatch_tool_calls` defaults to them. Unknown
schema (none sent, or no `properties`) means *skip the check*, not *deny
everything* — denying would break every caller who never passed one, and
this check is a bound on model-chosen names, not an authorization system.
It bounds names only; validating values stays the tool's job.

**Bad arguments were fatal, which contradicted the Day 4 rule.** Day 4
established that a hallucinated tool *name* is trace data rather than a
traceback, but a hallucinated *argument* name still escaped as a
`TypeError` from `fn(**args)` and killed the agent loop — the same class
of model error, one level down, handled the opposite way. `signature.bind`
now catches unexpected and missing arguments before the call, so every
"the model got the call wrong" case lands in the same errored-span path.
Tools that raise while *executing* still propagate: that's the caller's
code failing, and swallowing it would hide a real bug behind a trace entry.

The split is now cleanly "wrong call" (recorded, fed back, recoverable)
vs. "broken tool" (raised), where before it was drawn accidentally at
whichever line happened to throw first.

## Day 4b — provider portability (no adapter changes)

Switching off OpenAI (cost) turned out to need **zero** adapter changes,
which is the Day 4 "never import `openai`, read fields structurally"
decision paying off earlier than expected. xAI, Groq, and Ollama all
expose OpenAI-compatible endpoints, so a `base_url` swap is the whole
migration; tracing, token capture, tool dispatch, and schema validation
were verified unmodified against all three response shapes.

Worth stating plainly since the module is named `adapters/openai.py`:
**it targets the wire format, not the vendor.** Renaming it to something
like `openai_compatible.py` would be more literally accurate, but the
format genuinely is OpenAI's — every other vendor documents themselves as
compatible *with* it — and a rename is a breaking import change for no
functional gain. Keeping the name and documenting the distinction is the
better trade until there's a second, genuinely different protocol to
adapt (Anthropic's `input_tokens`/`output_tokens` and content-block
shape would be that, and it'd be a sibling module rather than a rewrite).

The example grew a `--provider` table rather than a bare `--live` flag, so
the provider-specific config sits in one dataclass and the agent loop
stays identical across all of them — which is also the clearest available
demonstration of the portability claim.

## Next (Day 5)

The HTML/JS timeline viewer — `viewer/` still has only the text renderer,
and `_build_children` is already the tree-building step a real UI needs
(that split was the point of Day 3). FastAPI and uvicorn have been
dependencies since Day 1 for exactly this. Streaming responses are the
known gap in the adapter: `create(stream=True)` returns an iterator, so
the current code records an empty response and a duration that only
measures time-to-first-chunk. Wrapping the iterator to accumulate deltas
and close the span at the end is the fix, and it wants its own day.
