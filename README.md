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

Early build, in progress (v0.1.0 not yet tagged). See `docs/architecture.md`
for design notes as they're written.

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
