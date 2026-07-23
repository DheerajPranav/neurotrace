# LOOPS — how work moves through this repo

The full agentic-swe-kit loop tooling (`tools/scaffold.sh`, `graphizer.mjs`, `AGENT-ADAPTERS.md`)
isn't present in this Claude install — only `SKILL.md` instructions and the `agentic-swe-master`
reference skill are. These loop definitions are written by hand to match the genesis SKILL.md's
intent for this repo's actual size (1267 LOC, 4 milestones, one contributor). Don't reintroduce
process heavier than the project warrants.

## G0 — Existence Pre-Flight (run before starting any milestone)

Before touching code for milestone `Mn`:
1. Run `Mn`'s demo command from `PLAN.md` on the current `main`. If it already passes, the
   milestone may already be done (or was miscut) — stop and report, don't redo.
2. Re-read `Mn`'s freeze boundary. Confirm the planned change doesn't cross it.
3. `git status` clean, on `main`, no stray uncommitted work from a prior session.

## L1 — BUILD

1. Implement the milestone's outcome exactly as scoped in `PLAN.md` — no drive-by refactors, no
   scope creep into the next milestone's territory, no touching files outside the milestone's
   freeze boundary.
2. Write the test(s) named in the milestone's demo command as you go, not after — they're part of
   the outcome, not a formality.
3. Run the milestone's demo command yourself. If it doesn't pass, you're not done with BUILD.
4. Run the *full* suite (`python -m pytest -q`) before calling BUILD finished — a milestone that
   breaks an unrelated existing test is not done, it's a regression.
5. Update `CURRENT.md` with what changed and why, then hand off to VERIFY.

## L4 — VERIFY (always a separate pass from the maker)

VERIFY does not trust BUILD's own summary of what it did. It:
1. Re-reads the milestone's gate text in `DONE.html` §3 — not the maker's notes.
2. From a clean state (re-check `git diff` against what BUILD claims to have touched — flag
   anything outside the freeze boundary), re-runs the exact demo command from `PLAN.md`.
3. Runs the full test suite independently.
4. Checks the invariants in `context-graph.json` still hold (especially
   `no-crash-propagation` and `trace-data-is-unencrypted-by-design` — these are easy to violate
   accidentally while fixing something else).
5. Only then marks the milestone done in `CURRENT.md` and `PLAN.md`.

If VERIFY finds a gap, it goes back to BUILD with a specific, concrete failure — not "looks fine,
minor nit," but exactly which gate line in `DONE.html` isn't met and why.

## Why no L2/L3 here

The full agentic-swe-kit loop vocabulary implies more stages (review, integration test, etc.)
than a 4-milestone pass on a 1267-line codebase needs. BUILD's own step 4 (full suite before
handoff) absorbs what a separate TEST loop would otherwise do. If this plan grows past the
current 4 milestones or gains contributors, split BUILD's step 4 into its own L2 TEST loop rather
than inventing ceremony now for a problem that doesn't exist yet.
