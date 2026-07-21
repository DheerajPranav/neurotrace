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

## Day 5 — JSON API server

**`create_app(db_path)` returns an app, not a module-level `app`.** The
usual FastAPI shape is a global instantiated at import time, which would
force the db path in through an environment variable and make two apps
over two different databases impossible. A factory keeps the path an
argument, which is also what lets the tests run several apps in one
process without touching global state.

**A connection per request, not the shared one `SQLiteStorage` already
holds.** FastAPI runs sync endpoints in a worker threadpool, and sqlite3
refuses a connection used from a thread other than the one that created
it — so reusing the tracer's single-connection design raises
`ProgrammingError` on whichever request happens to land on a second
thread. Opening per request costs microseconds against a local file and
leaves the server with no shared mutable state. Verified by a test that
issues repeated requests rather than one, since a single request passes
either way.

**Missing db is an error, not an empty result.** `SQLiteStorage` creates
its schema on connect, so pointing the server at a typo'd path would
otherwise produce a new empty database and an API reporting zero traces —
the failure looks like "no traces recorded" instead of "wrong path."
`create_app` raises `FileNotFoundError`; the CLI turns that into
stderr + exit 1, consistent with Day 3's rule that user-facing conditions
aren't tracebacks.

**Flat and tree are separate endpoints.** `/api/traces/{id}` serves the
events as stored, `/api/traces/{id}/tree` serves them nested. Both exist
because they answer different questions: the flat form is what the
storage layer actually holds (and what an exporter or a diff would want),
the tree is what a timeline draws. Resolving nesting server-side means
Day 6's UI renders a structure instead of re-deriving one — and it's the
same resolution the text renderer does, so `_build_children` moved out of
`render.py` into `viewer/tree.py` rather than being reimplemented in JS.
That split was the stated point of Day 3; this is the day it paid off.

**`children_by_parent` now re-attaches orphans as roots.** An event whose
`parent_id` names an event not present in the trace was previously
unreachable from the root walk and silently dropped from the timeline.
A partial save shouldn't make spans disappear — losing an event's nesting
is a much smaller lie than losing the event.

**No pydantic response models.** Endpoints return the same dicts
`to_dict()` already produces. Mirroring the event schema in pydantic
would reintroduce exactly the per-type rigidity Day 1 rejected, on a
`payload` that is deliberately free-form, and it would have to be
rewritten for every adapter that shapes a payload differently.

**Read-only, loopback by default.** There are no write endpoints — writes
belong to `Tracer`, in the process being traced. The default bind is
`127.0.0.1` rather than `0.0.0.0` because a trace holds prompts, tool
arguments, and results verbatim (see README "Data handling"); serving
that to the local network by default would be a poor trade for
convenience. No CORS middleware either: Day 6's UI will be served by this
same app, so permissive cross-origin headers would only widen who can
read the traces without enabling anything the project needs.

**Summaries got their own storage method.** `/api/traces` wants "which
runs are here and did any fail," and answering it through `list_traces()`
loads every event of every run — one full load per trace, per request.
`list_trace_summaries()` is one aggregate query with counts.
`TraceStorage` provides a concrete default derived from `list_traces()`,
so it's an opt-in optimization rather than a new abstract method that
breaks other backends. `neurotrace list` uses it too, and now shows event
and error counts.

## Day 6 — browser timeline

**One self-contained HTML file, not a framework app.** The whole UI is
`viewer/static/index.html` — vanilla JS, inline CSS, no build step, no
dependency to install or version. A React/bundler front end would be the
conventional choice and the wrong one here: it adds a toolchain and a
`node_modules` to a Python package whose entire UI is a list and a tree, and
it would need its own release process alongside the wheel. The page is small
enough that plain DOM code is shorter than the config a framework would need.

**Served by the same app at `GET /`, from disk per request.** The file ships
inside the package (`Path(__file__).parent / "static"`), so a wheel install
serves the page too, not just a source checkout — there's a test asserting
that. Serving it from the app the API already runs is what lets Day 5's "no
CORS" decision stand: same origin, so the page's `fetch` calls need no
cross-origin headers, and nothing widens who can read a trace. Reading the
file per request (rather than caching it at startup) costs a local file read
and means editing the page during development needs no server restart.

**No external requests, and trace content is text, never markup.** Two
security properties, both tested. The page pulls no script, style, or font
off a CDN: a trace holds prompts and tool results verbatim, so a viewer that
phoned out would leak exactly the data the loopback bind protects — the test
greps the served HTML for any absolute or protocol-relative `src`/`href`.
And every value derived from a trace goes into the DOM through `textContent`,
never `innerHTML`: payloads carry model output and tool results, which are
untrusted strings, so rendering them as HTML would make the viewer a
stored-XSS surface. This is the browser-side continuation of Day 4a's stance
that trace content is data to display, not code to run.

**Nesting is consumed, not re-derived.** The page renders
`/api/traces/{id}/tree` directly — the `children` arrays are already the
shape it draws. That's the Day 5 decision to resolve the tree server-side
paying off: the JS walks a structure instead of reimplementing
`children_by_parent` in a second language. Per-span duration bars scale to
the slowest span in the same trace, with a minimum visible width so a
sub-millisecond span still shows.

## Day 7 — release (v0.1.0)

**Tagging what exists, not adding scope.** Day 7 is packaging and docs: an
an Apache-2.0 `LICENSE`, a `CHANGELOG.md`, PyPI metadata (authors, classifiers,
keywords, URLs), and bringing README, the architecture notes, and the
plain-language explainer current. The public repo had no license until now,
which is "all rights reserved" by default — a worse state for a tool meant to
be used than an explicit permissive license.

**Streaming stays a known limitation, documented rather than rushed.**
`create(stream=True)` returns an iterator, so the adapter still records an
empty response and a duration that only measures time-to-first-chunk. The fix
— wrapping the iterator to accumulate deltas and close the span when it's
exhausted — is real work with its own edge cases (a consumer that abandons
the iterator early, usage totals that only arrive in the final chunk), and
shipping it half-done would be worse than naming it in the changelog. It's
the first thing after 0.1.0, not part of it.
