"""A traced streaming completion, runnable without an API key.

    python examples/streaming_agent.py
    neurotrace view traces.db

Mirrors `examples/openai_agent.py`'s offline-scripted pattern, but calls
`create(stream=True)` instead of a single blocking `create()` -- the case
that used to trace as an empty response (see CHANGELOG's Day 8 entry).
Chunks are printed as they arrive, the same way a real streaming UI would
consume them; the adapter assembles the full response and its timing
behind the scenes, so the trace ends up complete either way.
"""

from __future__ import annotations

from neurotrace import SQLiteStorage, Tracer
from neurotrace.adapters.openai import trace_openai


class _Obj:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def _chunk(content=None, usage=None):
    delta = _Obj(content=content)
    choices = [_Obj(delta=delta)] if content is not None else []
    return _Obj(choices=choices, usage=usage)


class ScriptedStreamingClient:
    """Replays a fixed streamed response, one word-chunk at a time."""

    def __init__(self):
        self.chat = _Obj(completions=self)
        words = ["It's", " 22C", " and", " clear", " in", " Lisbon."]
        self._stream = [_chunk(w) for w in words]
        self._stream.append(_chunk(usage=_Obj(prompt_tokens=13, completion_tokens=6)))

    def create(self, **kwargs):
        return iter(self._stream)


def main() -> None:
    storage = SQLiteStorage("traces.db")
    try:
        with Tracer(name="streaming-agent", storage=storage) as tracer:
            client = trace_openai(ScriptedStreamingClient(), tracer)
            stream = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "What's the weather in Lisbon?"}],
                stream=True,
            )
            for chunk in stream:
                if chunk.choices:
                    print(chunk.choices[0].delta.content, end="", flush=True)
            print()
    finally:
        storage.close()

    print("\ntrace saved -> traces.db\n  neurotrace view traces.db")


if __name__ == "__main__":
    main()
