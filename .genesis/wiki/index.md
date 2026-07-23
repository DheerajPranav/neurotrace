# Wiki index — agentic-swe-kit pointers for neurotrace

neurotrace is a developer tool, not an AI agent — it has no LLM reasoning of
its own. It sits in the **observability / developer-experience** slice of
the agentic-swe-kit's 20-phase lifecycle, with a hard security edge because
of what it stores. These are the phases that actually apply; the rest
(multi-agent orchestration, RAG, memory architecture, cost routing, ...) are
not relevant to this codebase and are intentionally not loaded.

| Phase | Skill | Why it applies here |
|---|---|---|
| Phase 0 — Cognitive Design | `engineering-mindset` | Done — see `DONE.html` §1. neurotrace's cognitive job is zero-autonomy, deterministic instrumentation; skipping this would have led to over-building "smart" trace analysis nobody asked for. |
| Phase 10 — Observability & Tracing | `production-readiness` + `llmops-ai-agents` | This *is* the product. The gate ("every span captures latency + token count + tool result") is already met for LLM/tool calls; not yet met for streaming spans (known gap). |
| Phase 11 — Security Architecture | `security-engineering` | Traces contain unredacted prompts/secrets by design (`context-graph.json` invariant `trace-data-is-unencrypted-by-design`). No threat model doc exists yet; no redaction hook exists yet. This is the single biggest robustness gap. |
| Phase 12 — Reliability Engineering | `production-readiness` + `distributed-systems` | The core promise is "the observer must not break the observed." Partial-trace-on-exception already holds for the tracer; storage I/O has no timeout/circuit-breaker, and streaming isn't handled at all. |
| Phase 17 — Developer Experience | `engineering-mindset` + `modular-architecture` | CLI + browser viewer already exist. Gaps: no replay of a failed run's exact inputs, no filtering/search across traces. |
| Phase 18 — CI/CD for AI Systems | `production-readiness` + `llmops-ai-agents` | Currently **entirely missing** — no `.github/workflows`, no automated gate on the 58-test suite. Cheapest, highest-leverage fix available. |

## Explicitly out of scope for this project (do not load)

- Phase 4/8 (workflow orchestration, multi-agent) — neurotrace doesn't run agents, it observes them.
- Phase 6 (memory architecture), Phase 7 (tooling/sandboxing as *agent* tools) — not applicable; `dispatch_tool_calls`'s schema validation is a security boundary, not a memory or sandboxing concern.
- Phase 9 (eval systems in the LLM-as-judge sense) — no model output to judge. The closest analog is the pytest regression suite, folded into Phase 18 instead of treated as its own phase.
- Phase 13/14/15/16/19/20 — infra/deployment, data pipelines, compliance, cost routing, HITL, continuous learning: none apply to a local, single-process, loopback-bound tool.

See `agentic-swe-master` (`swe-foundations/agentic-swe-master/SKILL.md`) for the full 20-phase reference if scope ever grows (e.g. a hosted multi-user trace store would reopen Phase 13/15).
