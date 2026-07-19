# NeuroTrace

A trace debugger/visualizer for AI agent execution. Wraps an agent's
execution loop, captures every decision (LLM call, tool call, reasoning
step, error, retry), and gives you a timeline to inspect what happened
and why. Think Chrome DevTools, but for agent runs.

## Why

Agent frameworks make it easy to build a loop and hard to see inside it.
When an agent misbehaves — infinite tool loop, hallucinated arguments,
silently swallowed error — the only recourse is usually `print()` and
re-running. NeuroTrace captures the full execution trace once, so you
can inspect it after the fact instead of re-running blind.

## Status

Early build, in progress (v0.1.0 not yet tagged). Capture, storage, the
OpenAI adapter, and a terminal timeline work today; the HTML viewer and
streaming support don't yet. See `docs/architecture.md` for design notes
as they're written.

## Usage

Wrap your client and run your agent loop unchanged:

```python
from neurotrace import SQLiteStorage, Tracer
from neurotrace.adapters.openai import trace_openai

with Tracer(name="my-agent", storage=SQLiteStorage("traces.db")) as tracer:
    client = trace_openai(OpenAI(), tracer)

    response = client.chat.completions.create(model="gpt-4o", messages=messages)
    messages += client.dispatch_tool_calls(response, {"get_weather": get_weather})
```

Every completion becomes a traced span, and each tool the model asks for
nests under the call that requested it. Then inspect the run (timings below
are from a live run — the offline example reports ~0ms, since it never
actually calls anything):

```console
$ neurotrace view traces.db
Trace: weather-agent  (d4561a4d)  2026-07-19T18:56:11 -> 2026-07-19T18:56:11
├─ llm_call  gpt-4o  412.7ms
│  └─ tool_call  get_weather  1.2ms
├─ llm_call  gpt-4o  380.1ms
├─ llm_call  gpt-4o  291.5ms
│  └─ tool_call  book_flight  0.1ms
│     └─ error  [error: no tool named 'book_flight']
└─ llm_call  gpt-4o  244.8ms
```

`neurotrace list traces.db` shows every run in the file. For a full
working agent, see `examples/openai_agent.py` — it runs offline against a
scripted client, so no API key is needed:

```bash
python examples/openai_agent.py && neurotrace view traces.db
```

The `openai` package is not a dependency; the adapter reads responses
structurally, so it also accepts plain dicts and OpenAI-compatible clients.

## Project layout

```
src/neurotrace/
├── core/       # event schema, tracer, storage
├── adapters/   # framework-specific instrumentation (OpenAI, LangChain, ...)
└── viewer/     # server + timeline UI
examples/       # runnable example agents
tests/
docs/
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
