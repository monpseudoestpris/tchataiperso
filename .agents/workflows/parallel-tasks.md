---
description: Execute a complex engineering task using the Orchestrator + Subagents workflow and update HANDOFF.md
---

# Parallel Multi-Agent Execution Workflow (`/parallel-task`)

Follow this deterministic pipeline in strict accordance with `AGENTS.md`:

1. **Context & Handoff Check (Orchestrator)**
   - Read `HANDOFF.md` and run `git status --short`.
   - Cross-check `HANDOFF.md` against actual repository state.

2. **Investigation & Contract Definition**
   - If multiple areas of the codebase or external patterns need inspection, delegate read-only exploration to `@investigator`.
   - Define the shared contracts (interfaces, types) and partition the work into strictly disjoint file ownership sets.
   - Present the short execution plan to the user in French (if architectural/non-trivial) or proceed directly if routine and reversible.

3. **Scoped Implementation**
   - For independent modules, delegate each work package to `@implementer` with explicit file ownership and acceptance criteria (maximum 3 active agents total including Orchestrator).
   - If file edits overlap, execute sequentially.

4. **Integration & Verification**
   - Review all diffs produced by `@implementer`.
   - Delegate test execution and edge-case regression testing to `@verifier`.

5. **Handoff & Summary (Orchestrator Only)**
   - Update all 8 required sections of `HANDOFF.md` at the project root.
   - Report to the user in French: changes made, files affected, exact checks run with results, and any remaining risks.