"""Instrument an OpenAI-style client so an agent loop traces itself.

`trace_openai(client, tracer)` returns a drop-in proxy: every
`chat.completions.create(...)` becomes an `llm_call` span with the model,
messages, response, and token usage filled in, and every tool the model asks
for becomes a `tool_call` span nested under the completion that requested it.
Anything the proxy doesn't instrument is delegated to the real client, so
swapping `client` for the traced one doesn't change the rest of the code.

The `openai` package is deliberately never imported here — see
docs/architecture.md. Fields are read structurally (`_get`), so pydantic
response models, plain dicts, recorded fixtures, and other OpenAI-compatible
clients all work, and the tests don't need the SDK installed.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from neurotrace.core.tracer import Tracer

# Tool names come off the wire from the model, so they're matched against the
# caller's dict rather than trusted — a name with no entry is a hallucination
# to record, not a crash. See `dispatch_tool_calls`.
ToolMap = dict[str, Callable[..., Any]]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a mapping or an attribute-style object, whichever it is."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _describe_tool_calls(tool_calls: Any) -> str:
    described = []
    for tool_call in tool_calls or []:
        function = _get(tool_call, "function")
        name = _get(function, "name", "?")
        arguments = _get(function, "arguments", "")
        described.append(f"{name}({arguments})")
    if not described:
        return ""
    return "[tool_calls] " + ", ".join(described)


def _format_messages(messages: Any) -> str:
    """Flatten a messages list into the single prompt string Event expects.

    Lossy by design: the payload is for reading a timeline, not for replaying
    the request. A message with no content is an assistant turn that asked for
    tools, so it renders as the tool calls it requested.
    """
    lines = []
    for message in messages or []:
        role = _get(message, "role", "?")
        content = _get(message, "content")
        if content is None:
            content = _describe_tool_calls(_get(message, "tool_calls"))
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _first_message(response: Any) -> Any:
    """The assistant message off a completion response, or the message itself.

    Callers hand `dispatch_tool_calls` whichever they have in scope; a response
    has `choices`, a message doesn't.
    """
    if response is None:
        return None
    choices = _get(response, "choices")
    if choices is None:
        return response
    if not choices:
        return None
    return _get(choices[0], "message")


def _response_text(message: Any) -> str:
    if message is None:
        return ""
    content = _get(message, "content")
    if content:
        return content
    return _describe_tool_calls(_get(message, "tool_calls"))


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Decode a tool call's JSON `arguments` string into the args payload.

    Malformed JSON is kept verbatim under `_raw` instead of raising: the model
    emitting unparseable arguments is exactly the failure a trace exists to
    show, and losing it to a decode error defeats the point.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": parsed}


def _declared_properties(schemas: Any, name: str) -> set[str] | None:
    """Parameter names a tool's JSON schema actually offers the model.

    None means "unknown" (no schema supplied, tool not found, or a schema with
    no `properties`), which callers treat as "skip this check" rather than
    "allow nothing" — refusing every argument because a schema was omitted
    would break callers who never passed one.
    """
    for schema in schemas or []:
        function = _get(schema, "function") or schema
        if _get(function, "name") != name:
            continue
        parameters = _get(function, "parameters") or {}
        properties = _get(parameters, "properties")
        return None if properties is None else set(properties)
    return None


def _rejection_reason(
    name: str,
    args: dict[str, Any],
    fn: Callable[..., Any] | None,
    schemas: Any,
) -> str | None:
    """Why this tool call must not be executed, or None to go ahead.

    Everything the model controls — the tool name and every argument key — is
    checked here before anything is called, so a bad call becomes an errored
    span rather than an exception or an unintended invocation.
    """
    if fn is None:
        return f"no tool named {name!r}"

    # The schema is the contract shown to the model, so it bounds what the
    # model may set. Without this, a parameter that merely exists on the
    # Python function is model-settable even when the schema never offered
    # it — e.g. a `dry_run=True` or `allow_absolute=False` default silently
    # flipped by a prompt-injected tool call.
    declared = _declared_properties(schemas, name)
    if declared is not None:
        undeclared = sorted(set(args) - declared)
        if undeclared:
            return f"argument(s) not offered by the tool schema: {', '.join(undeclared)}"

    # Catches both unexpected keyword names and missing required parameters,
    # which would otherwise surface as a TypeError that kills the agent loop.
    try:
        inspect.signature(fn).bind(**args)
    except TypeError as exc:
        return f"invalid arguments: {exc}"
    except (ValueError, KeyError):
        pass  # not introspectable (some builtins/C functions) — let it run

    return None


def dispatch_tool_calls(
    tracer: Tracer,
    response: Any,
    tools: ToolMap,
    parent_id: str | None = None,
    schemas: Any = None,
) -> list[dict[str, Any]]:
    """Run the tools an assistant message asked for, tracing each one.

    Returns the `role="tool"` messages to append to the conversation before the
    next completion, so the caller's loop stays a normal OpenAI loop.

    Anything the model got wrong about *which* call to make — an unknown tool,
    an argument the schema never offered, a misspelled or missing parameter —
    is captured as an errored span and fed back as the tool result, so the loop
    continues and the model can recover. A tool that raises while *executing*
    is the caller's own code failing, so it propagates unmodified, consistent
    with every other span in the library.

    `schemas` is the same `tools=[...]` list handed to the API; when present,
    arguments are restricted to the parameters it declares. `TracedOpenAI`
    supplies it automatically from the last completion.
    """
    message = _first_message(response)
    tool_calls = _get(message, "tool_calls") or []

    results: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        function = _get(tool_call, "function")
        name = _get(function, "name", "")
        args = _parse_arguments(_get(function, "arguments"))
        fn = tools.get(name)

        with tracer.under(parent_id):
            with tracer.tool_call(tool_name=name, args=args) as span:
                reason = _rejection_reason(name, args, fn, schemas)
                if reason is not None:
                    # The recorded message carries no "error:" prefix — the
                    # renderer adds one. The model's copy keeps it, so the
                    # tool result reads as a failure in the conversation.
                    content = f"error: {reason}"
                    span.result = content
                    tracer.error(reason)
                else:
                    span.result = fn(**args)
                    content = str(span.result)

        results.append(
            {
                "role": "tool",
                "tool_call_id": _get(tool_call, "id", ""),
                "content": content,
            }
        )
    return results


class _TracedCompletions:
    def __init__(self, completions: Any, client: "TracedOpenAI") -> None:
        self._completions = completions
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        tracer = self._client.tracer
        with tracer.llm_call(
            model=kwargs.get("model", "unknown"),
            prompt=_format_messages(kwargs.get("messages")),
        ) as span:
            response = self._completions.create(**kwargs)
            span.response = _response_text(_first_message(response))

            usage = _get(response, "usage")
            if usage is not None:
                span.prompt_tokens = _get(usage, "prompt_tokens", 0) or 0
                span.completion_tokens = _get(usage, "completion_tokens", 0) or 0

            # Recorded so tool calls this response requests can nest under it
            # once the caller dispatches them, after this span has closed.
            self._client.last_llm_event_id = span.event_id
            # The schemas sent with the request are what the model was offered,
            # so they're the right bound to check its tool calls against.
            self._client.last_tool_schemas = kwargs.get("tools")
            return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _TracedChat:
    def __init__(self, chat: Any, client: "TracedOpenAI") -> None:
        self._chat = chat
        self.completions = _TracedCompletions(chat.completions, client)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class TracedOpenAI:
    """Proxy around an OpenAI client that traces completions and tool calls."""

    def __init__(self, client: Any, tracer: Tracer) -> None:
        self._client = client
        self.tracer = tracer
        self.last_llm_event_id: str | None = None
        self.last_tool_schemas: Any = None
        self.chat = _TracedChat(client.chat, self)

    def dispatch_tool_calls(
        self,
        response: Any,
        tools: ToolMap,
        parent_id: str | None = None,
        schemas: Any = None,
    ) -> list[dict[str, Any]]:
        """Run requested tools, nested under the completion that asked for them.

        `parent_id` defaults to the last traced completion, which is what makes
        the timeline a tree instead of a flat sequence of alternating spans.
        `schemas` defaults to the `tools=[...]` sent with that same completion,
        so argument checking is on by default without the caller repeating
        themselves.
        """
        return dispatch_tool_calls(
            self.tracer,
            response,
            tools,
            parent_id=self.last_llm_event_id if parent_id is None else parent_id,
            schemas=self.last_tool_schemas if schemas is None else schemas,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def trace_openai(client: Any, tracer: Tracer) -> TracedOpenAI:
    """Wrap an OpenAI client so its completions and tool calls land in `tracer`."""
    return TracedOpenAI(client, tracer)
