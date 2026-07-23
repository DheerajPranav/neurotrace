"""Optional redaction hooks for trace payloads.

Default neurotrace behavior stores prompts, tool arguments, and results
verbatim (see the "Data handling" section of README.md) -- that is what
makes a trace useful for debugging. This module exists for the cases where
verbatim storage is not acceptable: pass `redact=redact_secrets` (or your
own callable) to `Tracer` and it runs on every event just before that event
is written to storage. The in-process `Tracer.trace` object is left
untouched -- only the copy handed to storage is transformed. Nothing here
runs unless you opt in.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from neurotrace.core.events import Event

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style secret keys
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+", re.IGNORECASE),  # bearer tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ids
    re.compile(
        r"(api[_-]?key|api[_-]?secret|password)\s*[=:]\s*['\"]?[^\s'\"]{6,}",
        re.IGNORECASE,
    ),
]

_REPLACEMENT = "[REDACTED]"

_SENSITIVE_KEY_NAMES = re.compile(
    r"(api[_-]?key|api[_-]?secret|secret|password|token|authorization)$",
    re.IGNORECASE,
)


def _redact_string(value: str) -> str:
    for pattern in _PATTERNS:
        value = pattern.sub(_REPLACEMENT, value)
    return value


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {
            key: (_REPLACEMENT if isinstance(v, str) and _SENSITIVE_KEY_NAMES.search(str(key)) else _redact_value(v))
            for key, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def redact_secrets(event: Event) -> Event:
    """Best-effort redaction of common secret shapes.

    Scans every string in the event's payload, and its error message if it
    has one, for API-key- and bearer-token-shaped substrings and replaces
    matches with "[REDACTED]". It also replaces any string value whose dict
    key looks sensitive (`api_key`, `secret`, `password`, `token`,
    `authorization`, ...) outright, since a bare secret with no
    recognizable shape of its own (a random session token, for example) is
    still identifiable by where it's stored even when it isn't identifiable
    by its content.

    This is pattern matching against known shapes, not a guarantee -- it
    will not catch a secret that has neither a recognizable shape nor a
    telling key name (a customer's SSN, freeform PII). Treat it as a floor,
    not a ceiling, and pass your own stricter callable if you need one; any
    `Callable[[Event], Event]` works as a `Tracer(redact=...)` argument.
    """
    new_payload = _redact_value(event.payload)
    new_error = _redact_string(event.error) if event.error else event.error
    return replace(event, payload=new_payload, error=new_error)
