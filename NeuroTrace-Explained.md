# NeuroTrace, Explained

This document lives *outside* the `NeuroTrace/` project folder on purpose —
it's not part of the code, it's your personal notes so you always know
what's going on inside it, why, and what happened each day. I'll add a
new dated entry to the **Daily Log** at the bottom every day we work on
this. Everything above the log is background you should only need to
read once (though feel free to come back to it any time something feels
fuzzy).

---

## 1. What is NeuroTrace, in one sentence

**It's a tool that lets you watch, step-by-step, everything an AI agent
did during a task — instead of guessing why it broke.**

---

## 2. The problem, explained like you've never touched AI before

Imagine you hire an assistant and give them a task: "book me a flight to
Chicago." The assistant goes off, makes some phone calls, checks a
calendar, maybe messes something up, and comes back an hour later and
says "done" — or "sorry, it didn't work."

If it didn't work, you'd want to ask: *what exactly did you do? Who did
you call? What did they say? Where did it go wrong?*

An "AI agent" is a program that works the same way — you give it a goal
("find me the cheapest flight"), and it goes off on its own, calling
other programs and asking an AI model ("brain") what to do at each step,
in a loop, until it thinks it's done.

The problem: **today, most of that loop is invisible.** It happens, and
then you get an answer (or an error), and you have no easy way to see
the steps in between. If the agent gets stuck repeating itself, or makes
up an argument that doesn't exist, or silently retries five times before
giving up — you don't see any of that unless you were staring at raw
logs scrolling past in a terminal.

**NeuroTrace's job is to record every one of those steps and show them
to you afterward, in an organized, readable way** — similar to how your
web browser's "Inspect" / DevTools panel shows you every network request
a webpage made, instead of just showing you the final page.

---

## 3. The same problem, explained professionally

AI agents built on LLMs (large language models) operate as an
observation → reasoning → action loop: the agent calls an LLM to decide
what to do, optionally calls a tool (a function, an API, a database
query), observes the result, and repeats until it produces a final
answer or hits a stop condition.

Debugging this loop today typically means reading raw stdout logs or,
at best, whatever a specific framework's built-in tracing gives you
(and every framework — LangChain, LlamaIndex, raw OpenAI function
calling, CrewAI — does this differently, if at all). There's no
consistent, framework-agnostic way to capture *"here is the exact
sequence of LLM calls, tool calls, retries, and errors that happened in
this run, with timing and payloads,"* and then inspect it visually
after the fact.

NeuroTrace is an **observability layer for agent execution**: it wraps
an agent's loop, captures a structured event for every LLM call, tool
call, error, and retry (prompt/response, tokens, latency, tool
arguments and results, error messages), stores that sequence as a
"trace," and renders it as an inspectable timeline — analogous to
distributed tracing tools (Jaeger, Honeycomb) but purpose-built for
agent reasoning loops instead of microservice request chains.

---

## 4. Glossary — the words you'll keep seeing

| Term | Plain-language meaning |
|---|---|
| **Agent** | A program that uses an AI model in a loop to accomplish a goal, calling tools along the way. |
| **LLM call** | One "ask the AI brain a question, get an answer" round trip. Costs tokens, takes time. |
| **Tool call** | The agent using an external capability — a search function, a calculator, a database query — not the AI model itself. |
| **Trace** | The full recorded history of one agent run — a timeline of everything it did, start to finish. |
| **Event** | One single thing that happened during a run — one LLM call, one tool call, one error, one retry. A trace is a list of events. |
| **Schema** | The agreed-upon shape/structure of your data. "Every event has a type, a timestamp, and a payload" is a schema. |
| **Adapter** | A small piece of code that translates a specific framework's (LangChain, OpenAI, etc.) way of doing things into NeuroTrace's event format, so NeuroTrace can work with any of them. |
| **Payload** | The actual content/details carried by an event — e.g., for an LLM call event, the payload holds the prompt, the response, and token counts. |
| **Tracer** | The piece of code that sits "around" the agent's loop and actually does the recording — like a black-box flight recorder. |
| **Storage layer** | Where recorded traces get saved so you can look at them later (in this project: SQLite, a simple file-based database). |
| **Viewer** | The part you actually look at — a webpage that reads a trace and displays it as a timeline. |
| **CLI** | Command Line Interface — typing commands like `neurotrace view <trace_id>` instead of clicking buttons. |
| **Repo / repository** | The project folder, tracked by Git (version control), so every change is recorded and can be undone or reviewed. |
| **Commit** | A saved checkpoint of your code at a point in time, with a message describing what changed. |
| **Push** | Uploading your local commits to GitHub so they exist online / are backed up / are visible to others. |

---

## 5. How the pieces fit together

Think of it like a factory line:

```
Your agent runs
      ↓
Tracer watches it and writes down every step  →  "Events"
      ↓
Events get bundled into one "Trace" for the whole run
      ↓
Trace gets saved to a small local database (SQLite)
      ↓
Viewer reads that trace and draws it as a timeline in your browser
```

In the codebase, that maps to folders like this:

```
src/neurotrace/
├── core/       ← the recording equipment: what an "event" IS (events.py),
│                 the recorder itself (tracer.py, coming Day 2),
│                 and where recordings get saved (storage.py, coming Day 2)
├── adapters/   ← translators for specific AI frameworks (OpenAI, LangChain...)
└── viewer/     ← the webpage that displays a trace as a timeline
examples/       ← toy agents you can run to generate real traces to look at
tests/          ← automated checks that prove the code works as intended
docs/           ← technical design notes (the "why" behind decisions)
```

**Why build it in this order (core → adapters → viewer)?** Because the
viewer is useless without real data to show, and adapters are useless
without a place to send their data — so we build the recording
equipment first, then plug in translators for real frameworks, then
build the screen that displays it all. Building UI first would mean
staring at a pretty timeline with nothing real in it.

---

## 6. What the finished thing looks like

By Day 7, you'll be able to:

1. Run one of the example agents (`neurotrace run examples/simple_react_agent.py`)
2. It does its thing, and NeuroTrace silently records every LLM call and tool call it made
3. You run `neurotrace view <trace_id>`
4. A local webpage opens showing a chronological list: "10:03:01 — LLM call (420ms) → asked for a tool to use," "10:03:02 — Tool call: search('weather in Chicago') → result," etc., with errors/retries highlighted in red, and you can click to expand any step and see the full prompt/response or tool arguments.

That's the whole product for v0.1.0 — later versions could compare two runs side by side, auto-flag "this agent is stuck in a loop," estimate cost, etc., but those are stretch goals, not part of the 7-day MVP.

---

## 7. The 7-day build plan (recap)

| Day | What gets built |
|---|---|
| **1** ✅ | Project skeleton + the "Event" data format (the vocabulary everything else speaks) |
| **2** | The recorder ("Tracer") + local database storage |
| **3** | Actually capturing real LLM calls and tool calls with timing |
| **4** | Plugging into real OpenAI agent code + an example agent to test with |
| **5** | A small local web server that can hand back a trace as data |
| **6** | The actual visual timeline you look at in a browser |
| **7** | Command-line commands to tie it together, polish, first public release (v0.1.0) |

---

## 8. Daily Log

### Day 1 — 2026-07-16

**In plain terms:** Today we didn't build anything you can *see* run yet
— today was "designing the vocabulary." Before you can record what an
agent did, you have to decide *what counts as a thing worth recording,
and what shape does that recording take.* That's what we did.

**What we actually did, step by step:**

1. **Found your `NeuroTrace` folder** — it existed but was completely
   empty (no code yet).
2. **Set up the project skeleton** — created the folder structure shown
   in section 5 above, plus a `pyproject.toml` (a config file that tells
   Python "this is an installable package named `neurotrace`, here's
   what it depends on").
3. **Designed the "Event" format** (`src/neurotrace/core/events.py`) —
   this is the single most important decision of the whole project,
   because every other piece (recorder, storage, viewer, adapters) has
   to agree on what an "event" looks like. We went with: every event
   has a type (LLM call / tool call / error / retry / decision), a
   timestamp, how long it took, and a flexible "payload" holding the
   type-specific details (e.g. an LLM call's payload holds the prompt
   and response; a tool call's payload holds the tool name and
   arguments).
   - **Why this shape and not something more rigid?** Because different
     AI frameworks (LangChain vs. raw OpenAI vs. others) all describe
     "what happened" slightly differently, and a flexible payload means
     we don't have to redesign the core format every time we add
     support for a new framework. The tradeoff is we lose some
     automatic error-checking on the payload's contents — a reasonable
     trade for a project moving this fast. Full write-up in
     `docs/architecture.md` if you want the deeper reasoning later.
4. **Wrote automated tests** (`tests/test_events.py`) — 5 small checks
   that prove events get created correctly, survive being saved and
   reloaded, and get unique IDs. All 5 passed.
5. **Installed the project locally** in a virtual environment (an
   isolated Python setup just for this project, so it doesn't interfere
   with anything else on your machine) and confirmed it actually
   installs and runs cleanly.
6. **Set up version control (Git)** for the project and made the first
   commit — a "commit" is a saved snapshot of the code with a message
   explaining what changed and why. This is commit #1 of the project.
7. **Connected your GitHub account** — installed GitHub's command-line
   tool (`gh`), you logged in as `DheerajPranav` through your browser,
   and then we created a public repository (an online copy of the
   project) and pushed today's commit to it.

**Where things live now:**
- Local code: `/Users/dheerajpranav/Desktop/DeskTrux/Projects/Dheeraj/NeuroTrace`
- Online (GitHub): **https://github.com/DheerajPranav/neurotrace**
- This document: `/Users/dheerajpranav/Desktop/DeskTrux/Projects/Dheeraj/NeuroTrace-Explained.md`

**Bottom line for today:** nothing runnable/visual yet — that starts
Day 2 (the actual recorder) and becomes clearly visible by Day 6 (the
timeline UI). Today was pouring the foundation: deciding the shape of
the data everything else will be built on, and getting the project
safely backed up on GitHub.
