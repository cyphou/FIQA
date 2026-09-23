# Multi-Agent Environment

Thirteen agents under [.github/agents/](../.github/agents), each owning a declared set of
files. Ownership is enforced: `python scripts/check_agent_ownership.py` reports drift and
`tests/test_agents.py` fails the build on it. The audit covers **two** populations — the
**22** modules under `fabric_iq/`, and the **6** documents and skills that assert a
privacy, identity or retention claim or that a model reads as instruction.

## Roster

| Agent | Domain | Owns |
|-------|--------|------|
| `@orchestrator` | Run lifecycle, CLI, exit codes | `assess.py`, `__init__.py`, `errors.py`, `deployment.py`, `fabric/`, `docs/INSTALL.md` |
| `@collector` | Evidence acquisition, quotas, fixtures | `collectors/`, `examples/` |
| `@scorer` | Scoring maths, data model, rule primitives | `scoring.py`, `models.py`, `rules/base.py` |
| `@tenant` | Tenant and workspace rules | `rules/tenant_rules.py`, `rules/workspace_rules.py` |
| `@semantic` | Model and report rules | `rules/semantic_model_rules.py`, `rules/report_rules.py` |
| `@dataagent` | Data Agent rules, evaluation corpus | `rules/data_agent_rules.py` |
| `@preceptor` | Assessment quality review | `preceptor.py`, `docs/SELF_ASSESSMENT.md` |
| `@remediation` | Backlog, priority, effort | `remediation.py` |
| `@lakehouse` | Persistence and reporting | `lakehouse.py`, `reporting.py` |
| `@tester` | Tests, fixtures, ownership and evidence-sink gates | `tests/`, `scripts/check_agent_ownership.py`, `scripts/check_evidence_sinks.py` |
| `@readme` | Documentation accuracy | `README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/SCORING.md`, `docs/RULES.md`, `docs/AGENTS.md`, `docs/INTERPRETING_RESULTS.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/IDENTITY_AND_RETENTION.md`, `.github/skills/fabric-iq-readiness/SKILL.md` |
| `@roadmap-planner` | Sequencing and gates | `docs/ROADMAP.md` |
| `@security` | Privacy, scopes, retention | *(nothing — read-only by design)* |

`@security` deliberately owns no module. A reviewer who can edit the code they review
eventually reviews their own edits. That is why the privacy documentation it audits is
owned by another agent: the review stays independent, and the claim still has a name
against it.

### Documentation ownership — privacy, identity, retention and instruction

A promise about which identity is used, where evidence lands, and how long it is kept is
a promise to a customer; a Skill is the same kind of promise made to a model at prompt
time. `REQUIRED_DOCS` in `scripts/check_agent_ownership.py` names the accountable owner
of each such file, and the check fails if one is unclaimed, claimed twice, claimed by an
agent other than the one named, **or missing from the repository entirely** — otherwise
the guarantee could be met by deleting the document that carries it:

| Document | Accountable owner | Why it carries a claim |
|----------|-------------------|------------------------|
| `docs/IDENTITY_AND_RETENTION.md` | `@readme` | Names which identities are read, where they land, and how long they are kept |
| `docs/INTERPRETING_RESULTS.md` | `@readme` | Tells an operator how to act on a verdict, and is the path the console and the HTML report hardcode (`fabric_iq.reporting.INTERPRETATION_GUIDE`) |
| `.github/skills/fabric-iq-readiness/SKILL.md` | `@readme` | A model reads it as authoritative instruction and it restates engine-owned thresholds in prose |
| `docs/INSTALL.md` | `@orchestrator` | Tells an operator where evidence is written and which paths stay untracked |
| `docs/SELF_ASSESSMENT.md` | `@preceptor` | Publishes the tool's own readiness evidence and its retention |
| `fabric/README.md` | `@orchestrator` | Deployment surface: workspace items, lakehouse destination, run evidence — covered by the `fabric/` claim |

The list is explicit rather than inferred. A heuristic that guessed which file "looks
like" a privacy claim would let the gate widen or narrow itself without a review.

### Two Executable Gates

Both are Phase 5 release-gate criteria, and both are runnable rather than asserted:

```bash
python scripts/check_agent_ownership.py   # criterion 10: modules and privacy docs have exactly one owner
python scripts/check_evidence_sinks.py    # criterion 9: evidence sinks are ignored, tracked files are clean
```

`check_evidence_sinks.py` answers three questions against the real repository: does every
writer destination — including the output examples documented in Markdown — resolve to a
rule in a committed `.gitignore`; is any tracked file shadowed by those rules (a pattern
broad enough to catch every mart is broad enough to hide a fixture); and does any tracked
file carry a real tenant GUID, UPN, email or `onmicrosoft` host. Both checks are
heuristic gates. They reduce, and never replace, the mandatory pre-push privacy audit in
[shared.instructions.md](../.github/agents/shared.instructions.md).

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
python scripts/check_agent_ownership.py   # who owns what (modules and privacy docs)
python scripts/check_evidence_sinks.py    # evidence sinks stay ignored, tracked files stay clean
python -m unittest tests.test_agents      # roster and ownership integrity
python -m unittest tests.test_evidence_sinks  # evidence-sink hygiene as a test
python scripts/build_rules_doc.py         # regenerate docs/RULES.md after a rule change
```

Route a change to the agent that owns the file. If a change spans several owners, the
`@orchestrator` sequences it.
