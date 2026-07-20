"""A traced function-calling agent, runnable without an API key.

    python examples/openai_agent.py                  # offline, no key needed
    python examples/openai_agent.py --provider groq  # or openai / xai / ollama
    neurotrace view traces.db

Defaults to a scripted stand-in client so the example works offline and
always produces the same trace. `--provider` swaps in a real client.

The adapter speaks the OpenAI *wire format*, not the OpenAI *service*, and
never imports the `openai` package — so any provider exposing an
OpenAI-compatible endpoint works with the same code. Only the base_url and
model name below change between them; the agent loop and the tracing are
byte-identical. Ollama is the genuinely free option (it runs locally); the
hosted ones all bill per token.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from neurotrace import SQLiteStorage, Tracer
from neurotrace.adapters.openai import trace_openai


@dataclass(frozen=True)
class Provider:
    base_url: str
    model: str
    key_env: str | None  # None -> no auth (local)


# All four speak the same protocol; the adapter can't tell them apart.
# Model names drift — check the provider's docs if one 404s.
PROVIDERS = {
    "openai": Provider("https://api.openai.com/v1", "gpt-4o", "OPENAI_API_KEY"),
    "xai": Provider("https://api.x.ai/v1", "grok-2-latest", "XAI_API_KEY"),
    "groq": Provider("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "ollama": Provider("http://localhost:11434/v1", "qwen2.5", None),
}

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


def run_agent(client, tracer, question: str, model: str = "gpt-4o") -> str:
    """A plain tool-calling loop. Nothing here knows it's being traced."""
    messages = [{"role": "user", "content": question}]

    for _ in range(4):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SCHEMAS
        )
        message = response.choices[0].message

        if not getattr(message, "tool_calls", None):
            return message.content or ""

        messages.append(
            {"role": "assistant", "content": None, "tool_calls": message.tool_calls}
        )
        messages.extend(client.dispatch_tool_calls(response, TOOLS))

    return "(gave up)"


def build_client(provider_name: str):
    """Construct a real client, or the offline stand-in. The only
    provider-specific code in this file."""
    if provider_name == "scripted":
        return ScriptedClient(), "gpt-4o"

    provider = PROVIDERS[provider_name]

    # Checked before the import so a missing key reports itself even when the
    # SDK isn't installed — both are things the user has to fix, and a bare
    # ImportError traceback wouldn't mention the key at all.
    api_key = os.environ.get(provider.key_env) if provider.key_env else "not-needed"
    if not api_key:
        raise SystemExit(
            f"{provider.key_env} is not set. Export it, or run without "
            f"--provider for the offline scripted client."
        )

    # Imported lazily: the openai SDK is not a dependency of neurotrace, and
    # it's used here purely as an HTTP client for the shared wire format.
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit(
            "--provider needs the `openai` package as an HTTP client "
            "(neurotrace itself doesn't depend on it): pip install openai"
        )

    return OpenAI(base_url=provider.base_url, api_key=api_key), provider.model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="scripted",
        choices=["scripted", *PROVIDERS],
        help="scripted (default, offline) or a real OpenAI-compatible provider",
    )
    parser.add_argument("--db", default="traces.db")
    args = parser.parse_args()

    raw_client, model = build_client(args.provider)

    storage = SQLiteStorage(args.db)
    try:
        with Tracer(
            name="weather-agent", storage=storage, metadata={"provider": args.provider}
        ) as tracer:
            client = trace_openai(raw_client, tracer)
            answer = run_agent(client, tracer, "What's the weather in Lisbon?", model)
            print(answer)

            # A second turn, to show the hallucinated tool in the timeline.
            print(run_agent(client, tracer, "Now book me a flight.", model))
    finally:
        storage.close()

    print(f"\ntrace saved -> {args.db}\n  neurotrace view {args.db}")


if __name__ == "__main__":
    main()
