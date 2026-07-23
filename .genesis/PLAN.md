# PLAN — neurotrace robustness pass

Context: v0.1.0 shipped (7 days of history, 1267 LOC, 58 passing tests, 0
CI/CD). Goal of this pass is not new features — it's closing the gaps that
stand between "works on my machine" and "safe to depend on." Milestones are
ordered cheapest-and-highest-leverage first.

Each milestone: one outcome, one demo command, a freeze boundary (what NOT
to touch while working the milestone), assigned skills.

---

## M1 — CI/CD gate (currently zero)

**Outcome:** every push/PR runs the existing test suite + a lint pass
automatically. Right now correctness is trusted by hand; this makes it
enforced.

**Demo command:**
```bash
pip install -e ".[dev]" && ruff check src tests && python -m pytest -q
```
(same commands `.github/workflows/ci.yml` runs on push/PR — passing locally
means the gate would pass in CI)

**Freeze boundary:** no source changes in `src/neurotrace/` during this
milestone. If a lint pass surfaces real violations, log them for a follow-up
milestone rather than fixing inline — this milestone is infra-only.

**Skills:** `production-readiness`, `llmops-ai-agents` (Phase 18 gate)

**Status:** done

---

## M2 — Redaction hook (Phase 11 security gate)

**Outcome:** `Tracer`/`SQLiteStorage` accept an optional redaction hook
applied to event payloads before persistence. Default behavior is unchanged
(verbatim storage — see `context-graph.json` invariant
`trace-data-is-unencrypted-by-design`); this is additive, not a default
behavior change. Ship a best-effort built-in redactor (common secret
patterns: `Bearer `, `sk-`, `api_key=`) that users can opt into.

**Demo command:**
```bash
python -m pytest tests/test_redaction.py -v
```

**Freeze boundary:** don't touch the browser viewer or JSON API in this
milestone — redaction happens at write-time (tracer/storage), so nothing
downstream needs to change.

**Skills:** `security-engineering` (Phase 11 gate)

**Status:** done

---

## M3 — Streaming responses fully traced (known limitation)

**Outcome:** `create(stream=True)` through the OpenAI adapter produces a
span with the fully assembled response content and accurate timing
(time-to-first-chunk *and* total duration), not an empty response. The
wrapper must remain a transparent passthrough generator — the caller's
chunk-by-chunk consumption must be unaffected.

**Demo command:**
```bash
python examples/streaming_agent.py && neurotrace view traces.db
```
(new example script — mirrors `examples/openai_agent.py`'s offline-scripted
pattern so it needs no API key)

**Freeze boundary:** don't touch `core/tracer.py`'s span lifecycle
contract — streaming support is adapter-level (wrap the stream iterator),
not a new span type.

**Skills:** `llmops-ai-agents`, `production-readiness` (Phase 10/12 gates)

**Status:** done

---

## M4 — Storage failure can't crash the host agent (Phase 12 gate)

**Outcome:** if `SQLiteStorage.save_trace` raises (disk full, locked file,
permissions), the exception does not propagate into the agent loop being
traced — the invariant `no-crash-propagation` already holds for *tracer*
exceptions and must be extended to *storage* exceptions. Failures are
surfaced (a warning), never silently eaten forever. Also: guard against
double-instrumenting the same client (`trace_openai` called twice on one
client) so re-wrapping is idempotent, not additive spans.

**Demo command:**
```bash
python -m pytest tests/test_tracer_reliability.py -v
```

**Freeze boundary:** don't change the on-disk SQLite schema — this is
error-handling around existing writes, not a storage format change.

**Skills:** `production-readiness`, `distributed-systems` (Phase 12 gate)

**Status:** done

---

## Explicitly not in this plan

- **Anthropic-native adapter** (known limitation #3) — breadth, not
  robustness. Worth a follow-up plan once M1–M4 land.
- **Trace search/filter UI, replay** (Phase 17 gap) — real DX wins, but
  secondary to the above; would build on M1's CI gate to avoid regressing
  the viewer un-noticed.
