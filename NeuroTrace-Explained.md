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
│                 the recorder itself (tracer.py), and where recordings
│                 get saved (storage.py)
├── adapters/   ← translators for specific AI frameworks (OpenAI, LangChain...)
├── viewer/     ← turning a saved trace back into something you can look at:
│                 tree.py (rebuilds the shape), render.py (text timeline),
│                 server.py (hands traces out as data over HTTP)
└── cli.py      ← the `neurotrace` commands you type
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

1. Run the example agent (`python examples/openai_agent.py`)
2. It does its thing, and NeuroTrace silently records every LLM call and tool call it made
3. You run `neurotrace serve traces.db` and open the page it prints
4. A local webpage shows a chronological list: "10:03:01 — LLM call (420ms) → asked for a tool to use," "10:03:02 — Tool call: search('weather in Chicago') → result," etc., with errors/retries highlighted in red, and you can click to expand any step and see the full prompt/response or tool arguments.

Steps 1 and 2 have worked since Day 4. Step 3 works as of Day 5, but hands
back raw data rather than a page. Step 4 — the page itself — is Day 6.

That's the whole product for v0.1.0 — later versions could compare two runs side by side, auto-flag "this agent is stuck in a loop," estimate cost, etc., but those are stretch goals, not part of the 7-day MVP.

*(Note: the original Day 1 draft of this section guessed the commands would
be `neurotrace run …` and `neurotrace view <trace_id>`. The real ones came
out differently — you run your agent with plain Python, and `view` takes a
database file rather than a trace id. Corrected above so this section
matches what actually exists.)*

---

## 7. The 7-day build plan (recap)

| Day | What gets built |
|---|---|
| **1** ✅ | Project skeleton + the "Event" data format (the vocabulary everything else speaks) |
| **2** ✅ | The recorder ("Tracer") + local database storage |
| **3** ✅ | Command-line commands + a text timeline you can read in the terminal |
| **4** ✅ | Plugging into real OpenAI agent code + an example agent to test with |
| **4a** ✅ | *(unplanned)* Security fix: checking the tool calls the AI asks for before running them |
| **4b** ✅ | *(unplanned)* Running against cheaper/free AI providers instead of only OpenAI |
| **5** ✅ | A small local web server that can hand back a trace as data |
| **6** | The actual visual timeline you look at in a browser |
| **7** | Polish, documentation, first public release (v0.1.0) |

Days 4a and 4b weren't in the original plan — 4a came out of a security
review before making the repo public, and 4b came from wanting to stop
paying OpenAI for test runs. Day 3 also swapped order with the original
plan: the timeline renderer turned out to be more useful earlier than
"capturing real calls," which moved to Day 4.

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

---

### Day 2 — 2026-07-17

**In plain terms:** we built the tape recorder. Day 1 decided what a
"recording" looks like; today built the thing that actually presses
record, times each step, and saves the result to a file on your disk.

**What we actually did:**

1. **Built the `Tracer`** (`core/tracer.py`) — the piece you wrap around
   an agent run. You write `with Tracer(...) as tracer:` and everything
   inside that block gets recorded. Inside it, you can open smaller
   recordings for a single LLM call or a single tool call; each one
   times itself automatically.
2. **Made nested steps remember their parent.** If a tool gets called
   while handling an LLM call's answer, the recording notes "this tool
   belongs under that LLM call." That's what later lets us draw a tree
   instead of a flat list. The trick was giving each step its ID the
   moment it *starts* rather than when it finishes — otherwise a child
   step has no parent ID to point at yet.
3. **Built two places to save recordings** (`core/storage.py`) — one
   that keeps them in memory (fast, for tests) and one that writes to a
   SQLite file (a database that's just a single file, no server to run).
   Both work through the same interface, so anything using them doesn't
   care which it got.
4. **Made crashes still produce a recording.** If the agent blows up
   mid-run, the trace is still saved before the error escapes. That
   matters because a crashed run is exactly the one you want to inspect.
5. **Wrote 11 more tests.** All passed.

**Why it matters:** after today, a run could actually be recorded and
survive to disk. You still couldn't *look* at it — that's Day 3.

---

### Day 3 — 2026-07-18

**In plain terms:** today the recordings became readable. Up to now a
trace was rows in a database file; now you can type a command and see
your agent's run drawn as an indented tree.

**What we actually did:**

1. **Built the `neurotrace` command** (`cli.py`) with two subcommands:
   `list` (what runs are in this file?) and `view` (show me one).
2. **Made `view` guess what you want.** With no arguments it shows the
   most recent run, because right after running an agent the question is
   always "what just happened," not "let me look up an ID first."
3. **Built the text timeline** (`viewer/render.py`) — takes the flat list
   of recorded steps and reconstructs the tree from those parent links
   from Day 2, then draws it with `├─` and `└─` characters.
4. **Deliberately kept the drawing separate from the command.** The
   tree-rebuilding logic went in its own file rather than inside the CLI,
   because the browser viewer (Day 6) needs exactly the same logic. This
   sounds like fussiness; it paid off on Day 5.
5. **Made mistakes not look like crashes.** Typing a trace ID that
   doesn't exist prints a short message and exits, rather than dumping a
   wall of red Python error text. A typo isn't a bug in the program.

---

### Day 4 — 2026-07-20

**In plain terms:** until today, you had to manually tell NeuroTrace
about every step ("record that I'm about to call the AI... okay, done").
Today it became automatic. You change one line where your AI client is
created, and everything after that records itself.

**What we actually did:**

1. **Built the OpenAI adapter** (`adapters/openai.py`) — you wrap your AI
   client with `trace_openai(client, tracer)` and hand the result to your
   agent as normal. It passes everything through to the real client, but
   quietly records each call on the way past.
2. **Chose a wrapper over "patching."** The alternative was reaching into
   the OpenAI library and rewriting its internals at runtime. That works
   until OpenAI reorganises their code and everything breaks. A wrapper
   is explicit and doesn't break.
3. **Never imported the OpenAI package at all.** The adapter reads
   responses by shape rather than by type — "does this thing have a
   `choices` field?" rather than "is this an OpenAI object?" That
   sounded like a testing convenience at the time. On Day 4b it turned
   out to be the most valuable decision in the project.
4. **Solved the ordering puzzle.** The AI *asks* for a tool inside its
   answer, but the tool only *runs* after that answer has come back and
   its recording has already been closed. So we record the answer's ID
   and re-attach the tool recording underneath it afterwards. Without
   this the timeline is a flat alternating list and you lose the "this
   call asked for that tool" link — which is most of the point.
5. **Decided what counts as a crash.** If the AI asks for a tool that
   doesn't exist, that's the agent misbehaving — it belongs *in the
   trace*, and the loop carries on so the AI can recover. If your own
   tool code breaks while running, that's a real bug and it's allowed to
   crash normally. Hiding the second kind inside a trace entry would be
   burying a genuine problem.
6. **Wrote an example agent that needs no API key** — it replays a fixed,
   scripted conversation, including one where the AI asks for a
   `book_flight` tool it was never given, so the error path shows up in
   the very first trace anyone generates.

---

### Day 4a — 2026-07-20 (unplanned: security)

**In plain terms:** before making the repo public, we reviewed the code
for anything unsafe and found a real problem. Fixed it the same day.

**The problem:** when the AI asks to run a tool, it also chooses the
arguments. We were passing those straight into your Python function. But
a Python function can have settings that you never advertised to the AI:

```python
def read_file(path, allow_absolute=False):   # AI was only told about `path`
```

If someone slipped a malicious instruction into the AI's input (a real
attack called "prompt injection"), it could ask to run
`read_file(path=..., allow_absolute=True)` and flip a safety setting you
believed was private and unreachable.

**The fix:** the list of tools you show the AI is now treated as a
contract and *enforced*. Arguments are restricted to exactly what that
list advertises. We also started catching misspelled and missing
arguments, which previously crashed the whole agent — inconsistent, since
Day 4 had already decided a hallucinated tool *name* was trace data
rather than a crash. Now both are handled the same way.

**Nice detail:** this needed no extra work from you. The tool list was
already being sent to the AI, so the wrapper just remembers it and
applies it automatically.

**Honest limit, worth knowing:** this checks argument *names*, not
*values*. It stops the AI setting a parameter you never offered; it does
not stop it passing a bad value to one you did. Checking that a file path
stays inside an allowed folder is still your tool's own job.

---

### Day 4b — 2026-07-20 (unplanned: cost)

**In plain terms:** running tests against OpenAI costs money per run. We
made the project work with cheaper and free alternatives — and it took
essentially no code changes, because of a decision made on Day 4.

**What we actually did:**

1. **Confirmed it already worked.** xAI (Grok), Groq, and Ollama all
   accept requests in the same format OpenAI uses. Because the Day 4
   adapter reads responses by shape and never imports OpenAI's package,
   all three worked with **zero changes**. The entire migration is
   swapping a web address.
2. **Verified rather than assumed** — tracing, token counting, tool
   running, and the Day 4a security check were all tested against all
   three.
3. **Added a `--provider` flag to the example** so you can run the
   identical agent against any of them and compare the traces.
4. **Kept the file named `adapters/openai.py`,** even though it's not
   really OpenAI-specific any more. Renaming it would break every
   existing import for no functional gain. It's documented instead.

**Why this matters beyond saving money:** Ollama runs the AI model on
your own machine, so nothing leaves your computer at all. And because
every provider produces the same trace format, "is the cheap model good
enough?" becomes something you can measure instead of argue about.

---

### Day 5 — 2026-07-20

**In plain terms:** today we built the part that hands a trace out to
*other programs* — a small web server running on your own machine. This
is the bridge to Day 6's actual visual timeline: the webpage needs some
way to ask for the data it's going to draw, and that's what got built.

**What we actually did:**

1. **Built the server** (`viewer/server.py`) with four ways to ask for a
   trace: a list of all runs, one run as it's stored, one run already
   shaped into a tree, and one run as the same text the terminal prints.
   You start it with `neurotrace serve traces.db`.
2. **Moved the tree-rebuilding into its own file** (`viewer/tree.py`).
   Day 3 had deliberately kept this logic separate from the CLI on the
   grounds that a real UI would need it later. Today the server became
   that second user, so instead of copying the logic, both now share one
   copy. This is the Day 3 bet paying off.
3. **Hit a genuine bug and fixed it.** Sharing one database connection
   across web requests doesn't work: the web server handles requests on
   different threads, and SQLite refuses a connection used from a
   different thread than the one that opened it. The fix is opening a
   fresh connection per request — it takes microseconds against a local
   file. There's now a test that makes *several* requests rather than
   one, because a single request would have passed either way and hidden
   the problem.
4. **Made a wrong file path say so.** Pointing the server at a misspelled
   filename used to create a brand-new empty database and cheerfully
   report "zero traces" — so a typo looked identical to "you haven't
   recorded anything yet." It now says the file doesn't exist.
5. **Fixed a quiet data-loss bug in the timeline.** If a step pointed at
   a parent step that wasn't in the trace, it was silently dropped from
   the display entirely. Now it shows up at the top level instead —
   losing a step's indentation is a much smaller lie than losing the step.
6. **Made listing runs much cheaper.** Showing "which runs are in this
   file" used to load every prompt and every response of every run just
   to count them. It's now a single database query. As a bonus,
   `neurotrace list` now shows how many steps each run had and how many
   went wrong.
7. **Two deliberate safety choices.** The server is read-only — there's
   no way to change or delete a trace through it. And it's only reachable
   from your own machine by default, not from your network, because
   traces contain your prompts and tool data in plain text. You can
   override that, but you have to ask for it.
8. **Wrote 16 more tests** (55 total, all passing) and updated the
   README and architecture notes.

**Bottom line for today:** the data is now reachable by a webpage.
Tomorrow (Day 6) that webpage gets built, and the project finally becomes
something you *look at* rather than read in a terminal.
