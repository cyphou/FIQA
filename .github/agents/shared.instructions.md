---
description: "Shared rules for all agents in the IsFabricReadyForIQ project. USE FOR: enforcing project-wide constraints, scoring integrity, evidence discipline, and safety rules."
---

# Shared Project Rules — Fabric IQ Readiness Assessment

All agents MUST follow these rules. They apply to every file in the project.

## Pipeline Architecture

```
Tenant / Fabric APIs → [Collect] → Bronze evidence → [Normalize] → Silver inventory
                                                   → [Score] → Scorecards + Findings
                                                   → [Prioritize] → Remediation backlog
                                                   → [Review] → Preceptorship verdict
                                                   → [Persist] → Lakehouse Gold marts
```

- **Collection**: `fabric_iq/collectors/` — strictly read-only evidence acquisition
- **Rules**: `fabric_iq/rules/` — one deterministic check per readiness requirement
- **Scoring**: `fabric_iq/scoring.py` — rule outcomes to explainable scorecards
- **Review**: `fabric_iq/preceptor.py` — the quality gate over the assessment itself
- **Output**: `fabric_iq/remediation.py`, `fabric_iq/lakehouse.py`, `fabric_iq/reporting.py`
- **Tests**: `tests/` — `python -m unittest discover -s tests -t .`
- **Release gates**: `docs/ROADMAP.md` is authoritative for current scope and gates.

## The Three Results Rule (Non-Negotiable)

This project publishes **three independent results** per object. They must never be
merged, averaged, or substituted for one another:

1. **Eligibility** — binary. Does the object clear every blocking rule?
2. **Readiness score** — 0-100, weighted across dimensions.
3. **Confidence** — how much of the object we could actually observe.

A high score with low confidence is a *statement about our blind spots*, not an
endorsement. Any change that lets one of these three silently absorb another is a
defect, regardless of how much nicer the output looks.

## Hard Constraints

1. **No external dependencies** — Python standard library only for the core engine.
2. **Read-only collection** — the assessor never writes to a customer tenant, never
   enables a setting, never "fixes" an object. It reports. Remediation is a backlog
   item for a human owner, never an automated action.
3. **Missing evidence is never a pass and never a zero** — an unobservable rule
   returns `NOT_EVALUATED`. It lowers confidence; it must not move the score.
   Scoring an absence as failure invents findings; scoring it as success invents
   readiness. Both are worse than admitting the blind spot.
4. **A blocking failure caps the score at 39 and revokes eligibility** — no weighting,
   no averaging, and no "but everything else is green" may lift an object above the
   cap. A major failure caps at 59. Caps only ever lower a score, never raise one.
5. **Every finding carries evidence and a remediation** — a finding a human cannot
   reproduce or act on is noise. `Evidence(source, reference)` names where the claim
   came from; `remediation` names what to change and who owns it.
6. **Product limits are dated facts, not lore** — every hard limit encoded in a rule
   (5 data sources, 25x25 results, 200-character description budget, 10,000-character
   AI instructions, F2+/P1+ capacity) must cite its documentation in `docs` and be
   revalidated before each release. When a limit changes, the rule changes with it.
7. **Read before write** — never assume file contents from memory.
8. **Test after every change** — run `python -m unittest discover -s tests -t .`.
9. **Raise domain errors** — new failure paths raise a `fabric_iq.errors.AssessmentError`
   subclass (`CollectionError`, `ThrottlingError`, `NormalizationError`, `RuleError`,
   `ScoringError`, `PersistenceError`, `ConfigurationError`, `ReviewError`) instead of a
   bare `ValueError`/`RuntimeError`. Resilience boundaries catch the specific errors they
   expect, so genuine defects still surface. When a broad `except Exception` is genuinely
   required, keep it and state why on the same line.
10. **Generic code only — no tenant-specific logic** — rule behaviour derives from
    structural signals (object type, metadata completeness, configuration state), never
    from matching a specific customer workspace, model, report, or agent by name.
    Forbidden: `if workspace_name == 'Finance PROD'`, hardcoded tenant IDs, hardcoded
    capacity names. Fixtures use synthetic data only.
11. **Declare file ownership** — every module under `fabric_iq/` and under `scripts/`,
    and every document or Skill that carries a privacy, identity, retention or
    instruction claim, must be listed by exactly one agent in its "Your Files" block,
    before that agent's `## Constraints` heading. A gate script is owned on the same
    terms as a module: an unowned gate fails open, and nobody is accountable for
    noticing. To point at another owner write "owned by **@agent**"; to declare
    intentional sharing write "co-owned with @agent".
    `python scripts/check_agent_ownership.py` reports the current state and
    `tests/test_agents.py` fails the build on drift.
12. **Pre-push privacy and provenance audit** — see below. Required before every push.
13. **Production execution, storage, and consumption happen in Fabric, not on a
    laptop** — the deployed target is Notebook → `FabricIQReadiness` Lakehouse
    (Bronze/Silver/Gold via OneLake) → Direct Lake semantic model → report, exactly as
    `fabric_iq/deployment.py` and `fabric_iq/lakehouse.py` already implement. Running
    `assess.py` against a local folder or an external evidence store (for example
    `C:\FabricIQ-Evidence\`) is a development/test convenience only; it must never be
    presented as, or substituted for, a production run. A live proof of this pipeline
    counts only when the Notebook executes inside the workspace, writes Gold marts to
    OneLake, and the model/report are refreshed from there — not when evidence is
    pulled to a local machine through an interactive session. This does not relax rule
    2 or the identity/scope prerequisites of Sprint 5.1: the Notebook's own read-only
    service principal still needs prior `@security` review before any real collection.

### Documentation Gate

Before every implementation, release, or documentation update, consult `@readme`
(the Documentation Guardian). It checks `README.md`, `docs/ROADMAP.md`, `CHANGELOG.md`,
rule counts, link validity, and evidence status. After the change, run its post-update
review again. A stale claim, a broken reference, an invented metric, or an unverified
readiness claim blocks the update until the owning agent reconciles it.

## Python Conventions

- Python 3.12+ compatible
- `unittest.TestCase` for all test classes
- Comment only what needs clarification; the rule catalogue is the documentation
- Prefer the smallest change that solves the problem

## Learned Pitfalls (Global)

- `RuleOutcome.passed()` on missing data is the single most dangerous bug in this
  codebase — it manufactures readiness. Always `require(subject, ...)` first.
- A rule that raises is a rule that lies: `Rule.evaluate()` degrades `KeyError`,
  `TypeError`, `ValueError` and `AttributeError` into `NOT_EVALUATED`. Do not widen
  that tuple to `Exception` — a genuine defect must still surface.
- `Approved for Copilot` is an author's self-attestation, not objective proof.
  Never treat an endorsement flag as evidence of quality.
- A report is not individually approved for Copilot; the approval rides on the
  semantic model. Report rules score context and validation surface, not endorsement.
- Normalizing DAX by collapsing whitespace is not enough to detect duplicate measures;
  whitespace inside string literals is meaningful and must be preserved.
- Coverage below 50% forces `NOT_EVALUATED`. Publishing a score from a third of the
  evidence is how a readiness programme loses its credibility in one meeting.
- Scanner API quotas are real: 500 `getInfo` calls/hour, 16 concurrent scans,
  100 workspaces/request, `modifiedSince` at most 30 days. Design for resumption.
- Power BI Q&A is announced for retirement in December 2026 — add no new dependency
  on it.

## Mandatory Pre-Push Privacy Audit

Required before every `git push`, including documentation-only changes.

1. Inspect `git status`, the staged diff, and the complete list of staged paths.
2. Scan staged text for high-confidence secrets: API keys, passwords, bearer/JWT
   tokens, PATs, private URLs, emails, phone numbers, and — critically for this
   project — **tenant IDs, capacity IDs, workspace GUIDs, and service principal IDs**.
3. Review `tests/`, `examples/`, documentation, and fixtures for customer or account
   information, real workspace or model names, and private environment metadata.
4. Verify that every fixture is synthetic. This tool reads real tenants; a fixture
   captured from a live run is a data leak waiting for a commit.
5. Classify every finding as `synthetic`, `public with verified license`,
   `provenance-required`, or `sensitive`. Unresolved `provenance-required` or
   `sensitive` findings block the push.
6. Report the scan result in the final response.

## Preceptorship Loop — Quality Gate

This project runs **two** preceptorship loops. They share a threshold and a shape, and
nothing else. Conflating them loses one of the two gates.

| | Product loop — `@preceptor` | Development loop — `@change-preceptor` |
|---|---|---|
| Subject | an assessment run | a code, test, script or documentation change |
| When | inside the pipeline, after scoring | before the change lands |
| Verdict | publish the verdict, or block it | land the change, or send it back |

### 1. The Product Loop — `@preceptor`

Every assessment passes through the **preceptorship loop** before publication:

```
DRAFT (assessment run) → REVIEW (@preceptor) → APPROVE? (≥ 4★?)
     ↑                                            │
     │                    YES ────────────────────→ PUBLISH
     │                     NO ────────────────────→ COACH (feedback)
     │                                              │
     └──────────────────────────────────────────────┘
                   (max 3 cycles, then escalate)
```

### What Makes This Loop Different

In a migration project the reviewer scores the *generated artifact*. Here the reviewer
scores the **assessment itself**. The question is not "is this tenant ready?" but
"is this verdict defensible?" An assessment that confidently declares a tenant ready
on 40% evidence is a worse outcome than no assessment at all, because someone will
act on it.

### Rules

- After scoring, the pipeline invokes `@preceptor` for quality review.
- If scored < 4★, read the coaching feedback and fix within your domain.
- Do NOT ignore coaching items — address each one or explain why it does not apply.
- Do NOT weaken a rule, a cap, or a threshold to make a review pass. Lowering the bar
  to clear the bar is the one failure mode this loop exists to prevent.
- After 3 cycles, `@preceptor` escalates to the user (publish-with-caveats or block).
- The review is read-only — `@preceptor` never edits rules, scores, or collectors.

### 2. The Development Loop — `@change-preceptor`

Every change follows **Plan → Assign → Implement → Review**. `@orchestrator` is the
tech lead: it plans and assigns one owner per change. The owning specialist implements
inside the files it owns. `@change-preceptor` reviews before the change lands.

```
PLAN (@orchestrator) → ASSIGN (owning specialist) → IMPLEMENT
     ↑                                                  │
     │                                                  ↓
     │                          REVIEW (@change-preceptor) → APPROVE? (≥ 4.0★?)
     │                                                  │
     │                    YES ──────────────────────────→ LAND
     │                     NO ──────────────────────────→ COACH (the author)
     └──────────────────────────────────────────────────┘
                   (max 3 cycles, then escalate to the user)
```

It scores six dimensions: gate integrity, mutation proof, evidence discipline,
ownership and scope, contract preservation, environment honesty. It owns no file, so
it can never review its own edit, and it coaches rather than fixes.

The failure mode it exists to catch is **a gate that fails open**: a check that exits 0
when the thing it protects is absent, unparseable, or silently unmatched. That is worse
than no check, because it reports safety that is not there. A gate nobody has watched
fail has not been shown to work — demand the mutation, not the assertion.

### Rules For Both Loops

- If scored below the threshold, read the coaching feedback and fix within your domain.
- Do NOT weaken a rule, a cap, a threshold, or an assertion to clear a review.
- A reviewer never edits what it reviews; it coaches the owning agent.
- Three cycles, then escalate to the user. Never loop forever.

## Agent Roster

| Agent | Domain |
|-------|--------|
| `@orchestrator` | CLI, run lifecycle, cross-agent coordination |
| `@collector` | Evidence acquisition, normalization, API quotas |
| `@scorer` | Scoring engine, data model, rule primitives |
| `@tenant` | Tenant and workspace rules |
| `@semantic` | Semantic model and report rules |
| `@dataagent` | Fabric Data Agent rules and evaluation corpus |
| `@preceptor` | Preceptorship loop, assessment quality review |
| `@change-preceptor` | Development-time change review, gate integrity, coaching before merge |
| `@remediation` | Backlog construction, prioritisation, effort |
| `@lakehouse` | Medallion persistence, Gold marts, reporting |
| `@tester` | Test suite, fixtures, regression coverage, the gates that fail the build |
| `@readme` | Documentation accuracy, release claims, rule-catalogue generation |
| `@roadmap-planner` | Roadmap sequencing and gates |
| `@security` | Privacy audit, least-privilege, data handling |
