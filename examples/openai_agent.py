"""A traced OpenAI function-calling agent, runnable without an API key.

    python examples/openai_agent.py
    neurotrace view traces.db

Runs against a scripted stand-in client by default so the example works
offline and always produces the same trace. Pass --live to use the real
`openai` client instead (needs the package and OPENAI_API_KEY); the agent
loop below is identical either way — that's the point of the adapter.
"""

from __future__ import annotations

import argparse

from neurotrace import SQLiteStorage, Tracer
from neurotrace.adapters.openai import trace_openai

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Look up the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def get_weather(city: str) -> str:
    return f"{city}: 22C, clear"


TOOLS = {"get_weather": get_weather}


# --- scripted stand-in for the OpenAI SDK ------------------------------------
# Only the surface the adapter touches: chat.completions.create returning
# objects with .choices[0].message and .usage.


class _Obj:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def _response(content=None, tool_calls=None, prompt_tokens=0, completion_tokens=0):
    message = _Obj(content=content, tool_calls=tool_calls)
    return _Obj(
        choices=[_Obj(message=message)],
        usage=_Obj(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def _tool_call(id, name, arguments):
    return _Obj(id=id, function=_Obj(name=name, arguments=arguments))


class ScriptedClient:
    """Replays a fixed conversation: ask for a tool, then answer, then hallucinate."""

    def __init__(self):
        self.chat = _Obj(completions=self)
        self._script = [
            _response(
                tool_calls=[_tool_call("call_1", "get_weather", '{"city": "Lisbon"}')],
                prompt_tokens=42,
                completion_tokens=18,
            ),
            _response(
                content="It's 22C and clear in Lisbon.",
                prompt_tokens=71,
                completion_tokens=12,
            ),
            # A tool the agent was never given — shows up in the trace as an
            # errored span instead of taking the process down.
            _response(
                tool_calls=[_tool_call("call_2", "book_flight", '{"to": "Lisbon"}')],
                prompt_tokens=88,
                completion_tokens=9,
            ),
            _response(content="I can't book flights.", prompt_tokens=94, completion_tokens=7),
        ]

    def create(self, **kwargs):
        return self._script.pop(0)


# --- the agent loop ----------------------------------------------------------


def run_agent(client, tracer, question: str) -> str:
    """A plain OpenAI tool-calling loop. Nothing here knows it's being traced."""
    messages = [{"role": "user", "content": question}]

    for _ in range(4):
        response = client.chat.completions.create(
            model="gpt-4o", messages=messages, tools=TOOL_SCHEMAS
        )
        message = response.choices[0].message

        if not getattr(message, "tool_calls", None):
            return message.content or ""

        messages.append(
            {"role": "assistant", "content": None, "tool_calls": message.tool_calls}
        )
        messages.extend(client.dispatch_tool_calls(response, TOOLS))

    return "(gave up)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use the real openai client")
    parser.add_argument("--db", default="traces.db")
    args = parser.parse_args()

    if args.live:
        from openai import OpenAI  # imported lazily: not a dependency of neurotrace

        raw_client = OpenAI()
    else:
        raw_client = ScriptedClient()

    storage = SQLiteStorage(args.db)
    try:
        with Tracer(name="weather-agent", storage=storage) as tracer:
            client = trace_openai(raw_client, tracer)
            answer = run_agent(client, tracer, "What's the weather in Lisbon?")
            print(answer)

            # A second turn, to show the hallucinated tool in the timeline.
            print(run_agent(client, tracer, "Now book me a flight."))
    finally:
        storage.close()

    print(f"\ntrace saved -> {args.db}\n  neurotrace view {args.db}")


if __name__ == "__main__":
    main()
