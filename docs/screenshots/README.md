# Viewer screenshots

Captured from the live browser viewer (`neurotrace serve`) against a real
trace produced by `examples/openai_agent.py` — the offline scripted run, which
deliberately includes a hallucinated `book_flight` tool so the error path is
visible. Rendered through Google Chrome, so these are the actual page, not
mockups.

| File | What it shows |
|---|---|
| `viewer-timeline.png` | The default view — run list, the nested timeline (a `get_weather` tool nested under its LLM call, the `book_flight` error nested under a later one), type badges, and per-span duration bars. |
| `viewer-llm-detail.png` | An LLM call expanded: model, duration, token counts, and the full prompt and response. |
| `viewer-error-detail.png` | The errored `book_flight` span expanded, showing the error detail (`no tool named 'book_flight'`). |
| `viewer-light-theme.png` | The same trace in the light theme, toggled from the header. |
