# Multi-Agent Environment

Thirteen agents under [.github/agents/](../.github/agents), each owning a declared set of
files. Ownership is enforced: `python scripts/check_agent_ownership.py` reports drift and
`tests/test_agents.py` fails the build on it.

## Roster

| Agent | Domain | Owns |
|-------|--------|------|
| `@orchestrator` | Run lifecycle, CLI, exit codes | `assess.py`, `__init__.py`, `errors.py` |
| `@collector` | Evidence acquisition, quotas, fixtures | `collectors/`, `examples/` |
| `@scorer` | Scoring maths, data model, rule primitives | `scoring.py`, `models.py`, `rules/base.py` |
| `@tenant` | Tenant and workspace rules | `rules/tenant_rules.py`, `rules/workspace_rules.py` |
| `@semantic` | Model and report rules | `rules/semantic_model_rules.py`, `rules/report_rules.py` |
| `@dataagent` | Data Agent rules, evaluation corpus | `rules/data_agent_rules.py` |
| `@preceptor` | Assessment quality review | `preceptor.py` |
| `@remediation` | Backlog, priority, effort | `remediation.py` |
| `@lakehouse` | Persistence and reporting | `lakehouse.py`, `reporting.py` |
| `@tester` | Tests, fixtures, ownership script | `tests/`, `scripts/check_agent_ownership.py` |
| `@readme` | Documentation accuracy | `README.md`, `CHANGELOG.md`, `docs/*` |
| `@roadmap-planner` | Sequencing and gates | `docs/ROADMAP.md` |
| `@security` | Privacy, scopes, retention | *(nothing — read-only by design)* |

`@security` deliberately owns no module. A reviewer who can edit the code they review
eventually reviews their own edits.

## Why Ownership Is Enforced

An unclaimed module has no agent to coach when the preceptorship loop raises a finding
against it. A doubly claimed module has two agents editing the same file with different
mental models. Both failure modes are silent until they cost a day.

## The Preceptorship Loop

```
DRAFT (assessment run) → REVIEW (@preceptor) → APPROVE? (≥ 4★?)
     ↑                                            │
     │                    YES ────────────────────→ PUBLISH
     │                     NO ────────────────────→ COACH (feedback)
     │                                              │
     └──────────────────────────────────────────────┘
                   (max 3 cycles, then escalate)
```

### What Is Being Reviewed

In a migration project the reviewer scores the *generated artifact*. Here it scores the
**assessment itself**. The question is not "is this tenant ready?" but "is this verdict
defensible?"

An assessment that confidently declares a tenant ready on 40% evidence is worse than no
assessment, because someone will act on it. That is the failure this loop exists to catch.

### Dimensions

| Dimension | Question | Coached agent |
|-----------|----------|---------------|
| `evidence_completeness` | Can every finding be reproduced from a named source? | `@collector` |
| `rule_coverage` | Did we evaluate enough of each object to speak about it? | `@collector` |
| `blocking_integrity` | Is anything published as ready despite a blocking failure? | `@scorer` |
| `remediation_actionability` | Does every failure have an owner, action and effort? | `@remediation` |
| `score_traceability` | Ruleset version, dimension breakdown, timestamp present? | `@scorer` |
| `freshness` | Do confidence and data recency support the verdict? | `@collector` |

`blocking_integrity` is the dimension that cannot be traded away. If a single object is
published as eligible while carrying a blocking finding, the entire scoring contract is
void and the review fails regardless of the other five looking healthy.

### Thresholds and Escalation

- **≥ 4.0★ average** → approved
- **< 4.0★** → coaching items routed to owning agents
- **3 cycles** → escalation with two explicit options: publish with recorded caveats, or
  block and re-collect

### Early Exit

The loop does not repair the run. If two consecutive cycles produce an identical coaching
signature, it exits immediately rather than consuming the remaining cycle. Re-running an
unchanged review would manufacture the appearance of diligence without adding evidence.

## Shared Rules

All agents are bound by [.github/agents/shared.instructions.md](../.github/agents/shared.instructions.md).
The rules that matter most:

1. Read-only collection — always, under every flag.
2. Missing evidence is `NOT_EVALUATED` — never a pass, never a zero.
3. Blocking caps at 39 and revokes eligibility.
4. Score, eligibility and confidence stay separate.
5. Standard library only.
6. Synthetic fixtures only.
7. Never weaken a rule, cap or threshold to make a review pass.

Rule 7 is the one the loop is designed to detect. Lowering the bar to clear the bar is
the natural response to a failing review, and it is the one response that destroys the
value of having a review at all.

## Working With The Agents

```bash
python scripts/check_agent_ownership.py   # who owns what
python -m unittest tests.test_agents      # roster and ownership integrity
python scripts/build_rules_doc.py         # regenerate docs/RULES.md after a rule change
```

Route a change to the agent that owns the file. If a change spans several owners, the
`@orchestrator` sequences it.
