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
| M1 | CI/CD gate | built + self-verified locally; **not yet pushed** (needs user go-ahead to commit/push before "ran green on GitHub" can be confirmed) |
| M2 | Redaction hook | not started |
| M3 | Streaming traced | not started |
| M4 | Storage failure isolation | not started |

## Next action

Awaiting user decision: commit + push M1 (to actually exercise the CI gate
on GitHub), and/or continue straight into M2 (redaction hook) locally.

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
  go-ahead first.
