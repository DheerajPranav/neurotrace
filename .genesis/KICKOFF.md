# KICKOFF — M1: CI/CD gate

Primed for the first BUILD loop. Read `PLAN.md` M1 and `DONE.html` §3 M1 for full context; this
file is the concrete first move, not a restatement.

## G0 Existence Pre-Flight

- [ ] Confirm no `.github/workflows/` exists yet (`find .github -type f` — expected: nothing)
- [ ] Confirm current baseline: `python -m pytest -q` → 58 passed
- [ ] `git status` clean on `main`

## L1 BUILD — concrete steps

1. Create `.github/workflows/ci.yml`:
   - Trigger: `push` and `pull_request`.
   - Matrix: Python 3.10–3.13 (pyproject already declares this range — the gate should actually
     exercise it, not just claim it).
   - Steps: checkout → setup-python → `pip install -e ".[dev]"` → `ruff check src tests` (add
     `ruff` to the `dev` extra in `pyproject.toml` if not already there — check first) →
     `python -m pytest -q`.
2. If `ruff` surfaces real violations in existing code: **do not fix them inline** (freeze
   boundary — M1 is infra-only). Note them in `CURRENT.md` under a new "Found during M1" line for
   a follow-up, and either scope the lint step to new/changed files only or accept the pass/fail
   as-is for this milestone — decide which, and say why in the commit.
3. Run the demo command locally exactly as CI would:
   ```bash
   pip install -e ".[dev]" && ruff check src tests && python -m pytest -q
   ```
4. Full suite already covered by step 3.

## L4 VERIFY — handoff criteria

- `.github/workflows/ci.yml` exists and its steps match what was run locally in step 3 above
  (verifier should diff the workflow file's run-commands against the demo command, not just
  check the file exists).
- No file outside `.github/` and possibly `pyproject.toml` (only if `ruff` needed adding to
  `dev` extras) was touched — anything else is a freeze-boundary violation.
- `DONE.html` §3 M1 gate text confirmed, not assumed.

## After M1 lands

Update `CURRENT.md`'s milestone table, then repeat G0 Existence Pre-Flight for M2 (redaction
hook) — see `PLAN.md` for its concrete steps.
