# CURRENT — rolling state

Last updated: 2026-07-23

## Where we are

Genesis spine just scaffolded (this session). No milestone work has started yet.
Baseline confirmed before any changes: 58/58 tests pass, no CI/CD exists,
no `tests/test_redaction.py` or `tests/test_tracer_reliability.py` yet,
streaming is the known-broken path per `CHANGELOG.md`.

## Milestone status

| # | Milestone | Status |
|---|---|---|
| M1 | CI/CD gate | **done** — pushed as `6668a21`, `gh run list` confirms `completed success` on the matrix run |
| M2 | Redaction hook | **done** |
| M3 | Streaming traced | in progress |
| M4 | Storage failure isolation | not started (scope note below) |

## Next action

M3: trace `create(stream=True)` fully in the OpenAI adapter.

**Note for M4:** while verifying M2, found that a user-supplied `redact`
callable raising inside `Tracer.__exit__` would currently propagate and
break the traced agent — the exact failure mode M4 is meant to close for
storage. Since it's the same code path (`__exit__`) and the same
`no-crash-propagation` invariant, fold this into M4 rather than patching it
twice: M4's fix should guard *both* `self._redact(e)` and
`self.storage.save_trace(...)`, not storage alone.

## Session log

- 2026-07-23 — Genesis spine created by hand (scaffold.sh/graphizer.mjs not
  present in this Claude install; templates/AGENT-ADAPTERS.md likewise
  absent). Ran G0 cognitive diagnostic against agentic-swe-master, mapped
  repo import graph, read CHANGELOG's "Known limitations" section, confirmed
  no `.github/` exists. Produced `context-graph.json`, `wiki/index.md`,
  `PLAN.md` (4 milestones), `DONE.html`, `LOOPS.md`, `KICKOFF.md`, this file.

- 2026-07-23 — M1 BUILD: added `ruff>=0.6` to `dev` extras, added
  `.github/workflows/ci.yml` (Python 3.10-3.13 matrix, `ruff check` +
  `pytest`), fixed the one lint violation ruff found (unused import in
  `tests/test_server.py` — logged here per KICKOFF.md's freeze-boundary
  instruction rather than silently folded into the CI commit). Demo command
  passes locally: `pip install -e ".[dev]" && ruff check src tests &&
  python -m pytest -q` → 58 passed. M1 self-VERIFY done inline (no separate
  agent spawned — respecting the standing instruction not to spawn agents
  unless asked; noting this as a real gap vs. the "separate verifier"
  principle in `LOOPS.md`/`DONE.html`, not pretending otherwise): diff scope
  checked (only `pyproject.toml`, `tests/test_server.py`, new
  `.github/workflows/ci.yml` — no `src/neurotrace/` logic touched, freeze
  boundary held), invariants in `context-graph.json` unaffected, full suite
  re-run independently. Not yet verifiable: whether the workflow actually
  runs green on GitHub — that requires a push, which needs the user's
  go-ahead first. **Resolved:** pushed as `6668a21`; `gh run list` confirmed
  `completed success`.

- 2026-07-23 — M2 BUILD: added `src/neurotrace/redaction.py`
  (`redact_secrets`, pattern-based on secret shapes plus sensitive key
  names, applied via a generic recursive payload walk) and an optional
  `redact` param on `Tracer.__init__`, applied once in `__exit__` to a copy
  of the trace before it's handed to storage — the in-process
  `self.trace` is never mutated. Exported `redact_secrets` from
  `neurotrace/__init__.py`. Updated README's "Data handling" section to
  document the hook instead of only the gap (DONE.html gate). Found and
  fixed a real bug during testing: the first pass only regex-matched
  string *content* (`api_key=...`), so a bare secret stored as a dict
  *value* under a key like `api_key` (no `=` in the string itself) slipped
  through — added a sensitive-key-name check alongside the content
  patterns. `tests/test_redaction.py` (9 tests) covers: content-pattern
  matches, nested-key matches, error-message redaction, verbatim-by-default
  regression, in-process-trace-untouched, and redaction still applying on
  the partial-trace-after-exception path. Full suite: 67 passed (58 + 9),
  lint clean. Freeze boundary held — no viewer/API files touched.
