# Copilot Instructions — IsFabricReadyForIQ

Assess whether a Power BI / Microsoft Fabric tenant and its objects are ready for
Fabric IQ and agentic experiences. Produce, per object, a **score**, an **eligibility
verdict**, a **confidence level**, and a **prioritised list of what to change**.

## Read First

- `.github/agents/shared.instructions.md` — project-wide rules, binding on every agent
- `docs/ROADMAP.md` — authoritative scope and release gates
- `docs/SCORING.md` — the scoring contract

## Non-Negotiables

1. **Read-only.** The assessor never modifies a tenant.
2. **Missing evidence is `NOT_EVALUATED`** — never a pass, never a zero.
3. **A blocking failure caps the score at 39** and revokes eligibility.
4. **Score, eligibility and confidence are three results**, never merged.
5. **Standard library only** for the core engine.
6. **Synthetic fixtures only.** Never commit tenant-derived data.

## Common Commands

```bash
python assess.py --inventory examples/sample_tenant --review --out artifacts
python assess.py --list-rules
python -m unittest discover -s tests -t .
python scripts/check_agent_ownership.py
```

## Agents

Invoke a specialist with `@name`. Each agent declares the files it owns; do not edit
another agent's files without routing through it.

`@orchestrator` `@collector` `@scorer` `@tenant` `@semantic` `@dataagent`
`@preceptor` `@remediation` `@lakehouse` `@tester` `@readme` `@roadmap-planner`
`@security`

`@preceptor` runs the preceptorship loop: DRAFT → REVIEW → APPROVE/COACH, 4★ threshold,
maximum 3 cycles, then escalation. It reviews the **assessment**, not the tenant.

## Language

Code, comments, rule text, docs and commit messages in English. User-facing conversation
may be in French.
