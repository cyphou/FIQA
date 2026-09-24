# Multi-Agent Environment

Fourteen agents under [.github/agents/](../.github/agents), twelve of them owning a
declared set of files. Ownership is enforced: `python scripts/check_agent_ownership.py`
reports drift and `tests/test_agents.py` fails the build on it. The audit covers **three**
populations — the **23** modules under `fabric_iq/`, the **4** gate and generator scripts
under `scripts/`, and the **7** documents and skills that assert a privacy, identity,
retention or collection-capability claim or that a model reads as instruction. The first
two are reported together as **27** audited modules, which is the count the check prints.

`scripts/` is audited on the same terms as the package, `__init__.py` included. An unowned
gate is worse than an unowned module: it keeps exiting 0 while the thing it was written to
catch walks past it, and no agent is accountable for noticing.

Two agents own nothing on purpose: `@change-preceptor`, which reviews a code change
before it lands, and `@security`, which audits privacy. Both are described below.

## Roster

| Agent | Domain | Owns |
|-------|--------|------|
| `@orchestrator` | Run lifecycle, CLI, exit codes | `assess.py`, `__init__.py`, `errors.py`, `deployment.py`, `fabric/`, `docs/INSTALL.md` |
| `@collector` | Evidence acquisition, quotas, fixtures | `collectors/`, `examples/`, `docs/API_REALITY_MATRIX.md` |
| `@scorer` | Scoring maths, data model, rule primitives | `scoring.py`, `models.py`, `rules/base.py` |
| `@tenant` | Tenant and workspace rules | `rules/tenant_rules.py`, `rules/workspace_rules.py` |
| `@semantic` | Model and report rules | `rules/semantic_model_rules.py`, `rules/report_rules.py` |
| `@dataagent` | Data Agent rules, evaluation corpus | `rules/data_agent_rules.py` |
| `@preceptor` | Assessment quality review — a **product feature** | `preceptor.py`, `docs/SELF_ASSESSMENT.md` |
| `@change-preceptor` | Code-change review before it lands — a **development role** | *(nothing — it reviews changes, it does not make them)* |
| `@remediation` | Backlog, priority, effort | `remediation.py` |
| `@lakehouse` | Persistence and reporting | `lakehouse.py`, `reporting.py` |
| `@tester` | Tests, fixtures, ownership and evidence-sink gates | `tests/`, `scripts/__init__.py`, `scripts/check_agent_ownership.py`, `scripts/check_evidence_sinks.py` |
| `@readme` | Documentation accuracy, rule-catalogue generation | `README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/SCORING.md`, `docs/RULES.md`, `docs/AGENTS.md`, `docs/INTERPRETING_RESULTS.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/IDENTITY_AND_RETENTION.md`, `.github/skills/fabric-iq-readiness/SKILL.md`, `scripts/build_rules_doc.py` |
| `@roadmap-planner` | Sequencing and gates | `docs/ROADMAP.md` |
| `@security` | Privacy, scopes, retention | *(nothing — read-only by design)* |

`@security` deliberately owns no module. A reviewer who can edit the code they review
eventually reviews their own edits. That is why the privacy documentation it audits is
owned by another agent: the review stays independent, and the claim still has a name
against it. `@change-preceptor` owns nothing for the same reason, and
`tests/test_agents.py` asserts both zero-ownership properties so a single added
backticked path cannot quietly hand either agent a file it reviews.

### Documentation ownership — privacy, identity, retention, capability and instruction

A promise about which identity is used, where evidence lands, and how long it is kept is
a promise to a customer; a statement about what the collectors can and cannot read is the
same kind of promise about the engine's own blind spots; a Skill is that promise made to
a model at prompt time. `REQUIRED_DOCS` in `scripts/check_agent_ownership.py` names the
accountable owner of each such file, and the check fails if one is unclaimed, claimed
twice, claimed by an agent other than the one named, **or missing from the repository
entirely** — otherwise the guarantee could be met by deleting the document that carries
it:

| Document | Accountable owner | Why it carries a claim |
|----------|-------------------|------------------------|
| `docs/IDENTITY_AND_RETENTION.md` | `@readme` | Names which identities are read, where they land, and how long they are kept |
| `docs/INTERPRETING_RESULTS.md` | `@readme` | Tells an operator how to act on a verdict, and is the path the console and the HTML report hardcode (`fabric_iq.reporting.INTERPRETATION_GUIDE`) |
| `.github/skills/fabric-iq-readiness/SKILL.md` | `@readme` | A model reads it as authoritative instruction and it restates engine-owned thresholds in prose |
| `docs/API_REALITY_MATRIX.md` | `@collector` | States field by field and endpoint by endpoint what a live read actually exposes; a stale row reads as evidence that was never collectable, and only the owner of `collectors/` can answer for it |
| `docs/INSTALL.md` | `@orchestrator` | Tells an operator where evidence is written and which paths stay untracked |
| `docs/SELF_ASSESSMENT.md` | `@preceptor` | Publishes the tool's own readiness evidence and its retention |
| `fabric/README.md` | `@orchestrator` | Deployment surface: workspace items, lakehouse destination, run evidence — covered by the `fabric/` claim |

The list is explicit rather than inferred. A heuristic that guessed which file "looks
like" a privacy claim would let the gate widen or narrow itself without a review.

### Script ownership — the gates and the generator

Everything under `scripts/` carries an owner for the same reason the modules do, but the
consequence of getting it wrong is sharper: a script that nobody maintains is usually a
script nobody reads, and a check nobody reads is a check that can start passing for the
wrong reason without anyone noticing.

| Script | Owner | Why that owner |
|--------|-------|----------------|
| `scripts/check_agent_ownership.py` | `@tester` | Ownership drift gate — a test made runnable |
| `scripts/check_evidence_sinks.py` | `@tester` | Evidence-sink hygiene gate — a test made runnable |
| `scripts/__init__.py` | `@tester` | Package marker that makes the gate scripts importable by the suite |
| `scripts/build_rules_doc.py` | `@readme` | Generates `docs/RULES.md`, which `@readme` owns; `--check` makes the catalogue-currency claim executable and CI runs it |

The split follows the artifact, not the folder: `@tester` owns the checks that fail the
build, `@readme` owns the generator whose output is a published document. Rule *content*
still belongs to the rule's owning agent — the generator only renders the registry.

### Two Executable Gates

Both are Phase 5 release-gate criteria, and both are runnable rather than asserted:

```bash
python scripts/check_agent_ownership.py   # criterion 10: every module under fabric_iq/ and scripts/, plus the privacy docs, has exactly one owner
python scripts/check_evidence_sinks.py    # criterion 9: evidence sinks are ignored, tracked files are clean
```

`check_evidence_sinks.py` answers three questions against the real repository: does every
writer destination — including the output examples documented in Markdown — resolve to a
rule in a committed `.gitignore`; is any tracked file shadowed by those rules (a pattern
broad enough to catch every mart is broad enough to hide a fixture); and does any tracked
file carry a real tenant GUID, UPN, email or `onmicrosoft` host. Both checks are
heuristic gates. They reduce, and never replace, the mandatory pre-push privacy audit in
[shared.instructions.md](../.github/agents/shared.instructions.md).

## Two Roles of Oversight

The roster is arranged as an AI-assisted engineering team with **two distinct oversight
roles** over the agents that write code:

| Role | Agent | Question it asks | Owns files |
|------|-------|------------------|------------|
| **Tech lead** | `@orchestrator` | "What is the next right piece of work, and who should do it?" | yes |
| **Preceptor** | `@change-preceptor` | "Does this change actually do what it reports?" | no |
| **Implementers** | the eleven file-owning specialists | "How do I build this in my domain?" | yes |

The eleven implementers are `@collector`, `@scorer`, `@tenant`, `@semantic`,
`@dataagent`, `@preceptor`, `@remediation`, `@lakehouse`, `@tester`, `@readme` and
`@roadmap-planner`. `@security` is a third reviewer, narrower in scope: it audits
privacy, scopes and retention rather than change quality.

Separating the two oversight roles is deliberate. A tech lead who also signs off the
work assesses a plan they authored, and the failure mode is predictable — the review
inherits the plan's blind spots. The preceptor never planned the change, so it reads
the diff as a stranger would.

### The Development Loop

```
              @orchestrator                              @change-preceptor
               (tech lead)                                  (preceptor)
                    │                                            │
                    ▼                                            ▼
   ──→ PLAN ──→ ASSIGN ──→ IMPLEMENT ──→ REVIEW ──→ ≥ 4.0★? ──YES──→ LAND
  │                        (specialist)                  │
  │                                                      NO
  └────────────── COACH (feedback to the owner) ─────────┘
                   (max 3 cycles, then the user arbitrates)
```

- **Plan** — `@orchestrator` decomposes the request against `docs/ROADMAP.md` and the
  scoring contract, and identifies which owners the change touches.
- **Assign** — work is routed to the agent that owns each file. A change spanning
  several owners stays sequenced by `@orchestrator`; it is not merged into one edit.
- **Implement** — the owning specialist makes the change and runs the gates.
- **Review** — `@change-preceptor` reads the change before it lands. It coaches the
  owning agent; it does not fix the code itself. Fixing would make it the author of
  work it is about to approve, which is the independence the role exists to preserve.

It scores six dimensions — gate integrity, mutation proof, evidence discipline,
ownership and scope, contract preservation, environment honesty — on the same scale the
assessment loop uses: **≥ 4.0★ approves**, below that the change is coached back to its
owner, and after **3 cycles** it escalates to the user with land-with-recorded-risk or
block stated as the two options. **Gate integrity scored 1★ blocks regardless of the
average**, by the same logic as the blocking cap: one check that manufactures confidence
voids the other five looking healthy.

`@orchestrator` plans and assigns; it does not grade its own assignment. "The tests are
green" is the claim under review, not a substitute for the review.

### Two Agents Carry The Word "Preceptor"

They are different roles with different subjects, and conflating them is the most
likely misreading of this document.

| | `@preceptor` | `@change-preceptor` |
|---|---|---|
| Reviews | the **assessment** a run produced | the **code change** before it lands |
| Exists at | run time — `fabric_iq/preceptor.py`, invoked by `--review` | development time — it ships no code |
| Asks | "is this verdict defensible?" | "does this change do what it reports?" |
| Owns | `preceptor.py`, `docs/SELF_ASSESSMENT.md` | nothing, by design |
| Outcome | ≥ 4★ publish, else coach; 3 cycles then escalate | ≥ 4★ land, else coach the author; 3 cycles then escalate |
| Pinned by | `tests/test_preceptor.py` | `tests/test_agents.py` — roster and zero ownership |

The short form: **`@preceptor` reviews the output, `@change-preceptor` reviews the
change.** One is a product feature a customer can run; the other is a development-time
role that never appears in a scorecard.

### Why The Change Preceptor Exists

Not as ceremony. It was added after a single session in which four gates **failed
open** — each reported a safety that was not there, and each was reported green by the
agent that wrote it:

| Failure | What was believed | What was true |
|---------|-------------------|---------------|
| Missing document | ownership gate exits 0, so ownership is sound | a required document was absent entirely, and an absent file has no owner to be wrong |
| Blank ignore pattern | `.gitignore` protects the evidence sinks | checked out CRLF, a blank line reads as a lone `\r` that matches every directory, so the check passed on nothing |
| Dot-leading path | the Skill is claimed by `@readme` | the claim parser dropped the leading dot, so `.github/skills/…` matched nothing and the claim was invisible |
| Local-only run | the commit is green | CI runs the suite on Linux under Python 3.12 **and** 3.13 plus six checks around it, and the commit went red there |

Each is now pinned by a regression: `missing_docs()` in
`scripts/check_agent_ownership.py` with `test_every_required_document_exists`,
`BlankIgnorePatternTests` in `tests/test_evidence_sinks.py`,
`test_a_dot_directory_path_is_recognised_as_a_claim` in `tests/test_agents.py`, and the
gate list in [.github/workflows/ci.yml](../.github/workflows/ci.yml) — the stdlib-only
dependency check, the suite, ownership, evidence sinks, rule-documentation currency, an
end-to-end run, and the assertion that a blocking finding still exits `2`.

A failing gate argues for itself. A gate that passes vacuously is indistinguishable from
a gate that works, from the inside, which is why the agent that wrote it is the worst
reader of it. `@change-preceptor` is the reader that did not write it.

## Why Ownership Is Enforced

An unclaimed module has no agent to coach when a review raises a finding against it —
whether that review is `@preceptor` coaching an assessment dimension or
`@change-preceptor` coaching a change. A doubly claimed module has two agents editing
the same file with different mental models. Both failure modes are silent until they
cost a day.

For a gate the silence lasts longer. A module that nobody owns eventually breaks loudly,
because something depends on it; a check that nobody owns keeps printing "clean" and is
indistinguishable from a check that works. That is why `scripts/` is inside the audited
universe rather than beside it: the gates themselves are held to the rule they enforce.

## The Assessment Preceptorship Loop — `@preceptor`

This loop belongs to `@preceptor` and is a **product feature**: it runs inside an
assessment, over the assessment. It is not the development loop described above.

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

Rule 7 is the one both review loops are designed to detect. Lowering the bar to clear
the bar is the natural response to a failing review, and it is the one response that
destroys the value of having a review at all.

## Working With The Agents

```bash
python scripts/check_agent_ownership.py   # who owns what (modules and privacy docs)
python scripts/check_evidence_sinks.py    # evidence sinks stay ignored, tracked files stay clean
python -m unittest tests.test_agents      # roster and ownership integrity
python -m unittest tests.test_evidence_sinks  # evidence-sink hygiene as a test
python scripts/build_rules_doc.py         # regenerate docs/RULES.md after a rule change
```

Route a change to the agent that owns the file. If a change spans several owners, the
`@orchestrator` sequences it, and `@change-preceptor` reviews it before it lands.
