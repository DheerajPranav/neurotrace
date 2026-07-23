# Changelog

All notable changes to NeuroTrace are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- CI on every push/PR (`.github/workflows/ci.yml`): `ruff check` + the full
  test suite across Python 3.10-3.13. Previously enforced by hand only.
- An optional `redact` hook on `Tracer`, applied to a copy of each event
  just before it's handed to storage; default (no hook) behavior is
  unchanged and still verbatim. Ships a best-effort built-in,
  `redact_secrets`, masking common secret shapes and sensitive key names.
  See README's "Data handling" section.
- `create(stream=True)` is now fully traced: the assembled response
  content, time-to-first-chunk, and total duration are all captured, where
  previously the span recorded an empty response (see `examples/streaming_agent.py`).
  Tool-call deltas inside a stream are not assembled yet — only text
  content and usage.
- `Tracer` no longer lets its own bookkeeping crash the traced run: a
  storage backend that fails to save (full disk, locked file) or a
  `redact` hook that raises now surfaces as a warning instead of
  propagating out of `__exit__` and masking whatever the traced code was
  actually doing.
- `trace_openai` is idempotent — wrapping an already-traced client returns
  it unchanged instead of nesting a second layer of instrumentation and
  recording two spans per real call.

### Fixed

- The browser viewer now follows the operating system's light/dark preference
  by default (via `prefers-color-scheme`) instead of always starting dark. An
  explicit choice from the header theme toggle still overrides the OS and
  persists across reloads.

## [0.1.0] — 2026-07-21

First tagged release: capture an agent run, store it, and inspect it as a
terminal timeline, a browser timeline, or JSON.

### Added

- **Event schema** (`core/events.py`) — one flat `Event` (type + free-form
  `payload`) plus a `Trace` container, chosen over a class-per-event
  hierarchy so it serializes to one SQLite table and every adapter can shape
  its own payload.
- **Tracer** (`core/tracer.py`) — a context manager wrapping an agent run,
  with nested `llm_call` / `tool_call` spans that time themselves and record
  their parent. A trace is saved even when the run raises.
- **Storage** (`core/storage.py`) — `TraceStorage` interface with an
  in-memory backend (tests) and a SQLite backend (on disk). `TraceSummary`
  and `list_trace_summaries()` answer "which runs, and did any fail" in one
  aggregate query instead of loading every event.
- **CLI** (`cli.py`) — `neurotrace list`, `view`, and `serve`. `view`
  defaults to the most recent run; mistyped ids and paths report on stderr
  rather than raising.
- **Text timeline** (`viewer/render.py`) — a Trace rendered as an indented
  `├─`/`└─` tree, reconstructed from `parent_id` links.
- **OpenAI adapter** (`adapters/openai.py`) — `trace_openai(client, tracer)`
  wraps a client so completions and tool calls trace themselves with no
  changes to the agent loop. It never imports `openai` and reads responses
  structurally, so it also drives xAI, Groq, and Ollama over the same OpenAI
  wire format. Dispatched tool calls are re-parented under the completion
  that requested them.
- **Tool-call validation** — `dispatch_tool_calls` bounds model-chosen
  arguments to the parameters the tool schema declares and checks them
  against the function signature before calling, so an unknown tool, an
  unadvertised parameter, or a misspelled argument becomes an errored span
  fed back to the model instead of running or raising.
- **JSON API** (`viewer/server.py`) — `create_app(db_path)` serves read-only
  endpoints: `GET /api/traces`, `/api/traces/{id}`, `/api/traces/{id}/tree`,
  and `/api/traces/{id}/text`. A connection per request (FastAPI's threadpool
  vs. sqlite3's per-thread connections); a missing database is an error, not
  an empty result.
- **Shared tree builder** (`viewer/tree.py`) — the `parent_id` → nested-tree
  resolution the text renderer and the API both use; re-attaches orphaned
  events as roots so a partial save never drops a span.
- **Browser viewer** — a single, self-contained `viewer/static/index.html`
  served at `GET /`: a trace list, an expandable timeline with per-span
  duration bars, prompt/response and tool argument/result detail panels, and
  errors highlighted. No external requests and no build step; trace content
  is rendered as text, never as HTML.
- **Example agent** (`examples/openai_agent.py`) — a tool-calling loop that
  runs offline against a scripted client (no API key), or against a real
  provider with `--provider`. It deliberately hallucinates a `book_flight`
  tool so the error path appears in the first trace anyone generates.
- Packaging metadata, an Apache-2.0 `LICENSE`, and this changelog.

### Security

- The server binds to `127.0.0.1` by default — a trace stores prompts, tool
  arguments, and results verbatim and unencrypted, so exposing it on the
  network is an explicit `--host` decision.
- The tool schema is enforced as a boundary against prompt-injected tool
  calls setting parameters that were never advertised to the model.

### Known limitations

- Streaming responses (`create(stream=True)`) aren't traced fully — the span
  records an empty response and only measures time-to-first-chunk.
- No redaction hook: sensitive data in prompts or tool arguments is written
  to the trace file as-is. Keep `.db` files out of version control.
- Only the OpenAI-compatible wire format is adapted; Anthropic's native shape
  would be a sibling adapter, not yet written.

[0.1.0]: https://github.com/DheerajPranav/neurotrace/releases/tag/v0.1.0
