<p align="center">
  <img src="docs/images/logo-fabric-iq-readiness.svg" alt="IsFabricReadyForIQ" width="180"/>
</p>

# 🧠 IsFabricReadyForIQ

**Fabric IQ & Agentic Readiness Assessment** — apply an evidence-aware readiness
ruleset to a Power BI / Microsoft Fabric tenant and its objects (tenant, workspace,
semantic model, report, Fabric Data Agent). The offline pipeline is fully testable;
live results remain bounded by the fields the APIs actually return.

| | |
|---|---|
| 🏷️ **Ruleset** | `2026.09.1` · package `0.1.0` |
| ✅ **Tests** | 348 tests passed — engine, rules, scoring, trends, preceptor, deployment, installer, self-assessment, evidence hygiene, reporting orientation, standalone guidance, Skill claim integrity |
| 🐍 **Python** | 3.12+ · zero external dependencies |
| 📜 **License** | Internal — see repository settings |
| 🎯 **Coverage** | 65 rules · 5 object types · 9 Gold marts · 14-agent environment |

For every object the tool produces:

| Result | Question it answers |
|--------|--------------------|
| 🚧 **Eligibility** | Does anything make this object structurally impossible to use? |
| 📈 **Readiness score** (0–100) | How well prepared is it, across weighted dimensions? |
| 🔍 **Confidence** | How much of it could we actually observe? |
| 🛠️ **Remediation backlog** | What to change, who owns it, how long it takes |

> [!IMPORTANT]
> These are **three separate results**. A high score with low confidence is a statement
> about blind spots, not an endorsement — the tool refuses to merge them into one
> reassuring number.

---

## 💡 Why This Exists

The building blocks exist — Scanner APIs, Fabric deployment surfaces, and Microsoft's
"prepare data for AI" guidance. This project collects available evidence, applies a
versioned rule catalogue, and produces explainable scorecards and an owned remediation
list. It does **not** yet execute a behavioural corpus against a real Data Agent, and it
does not turn unavailable API fields into a verdict.

---

## ⚡ Quick Start

```bash
# Score the synthetic sample tenant, with preceptorship review
python assess.py --inventory examples/sample_tenant --review --out artifacts

# Inspect the rule catalogue
python assess.py --list-rules

# Run the test suite
python -m unittest discover -s tests -t .

# Verify multi-agent file ownership
python scripts/check_agent_ownership.py

# Verify evidence sinks stay untracked and identifier-free
python scripts/check_evidence_sinks.py
```

No dependencies. Python 3.12+ standard library only.

`check_agent_ownership.py` asserts that every module under `fabric_iq/` is claimed by
exactly one agent, and that each document carrying a privacy, identity or retention
claim — or that a model reads as instruction, which is the same promise made at prompt
time — names exactly one accountable owner. Six documents and skills are in that
required set today; the check also fails if one of them is deleted outright, so the
guarantee cannot be met by removing the document that carries it.

`check_evidence_sinks.py` asserts three things about the repository as it stands: every
writer destination — defaults, the extensions the writers emit, and the `--out`,
`--lakehouse`, `--powerbi` and `--checkpoint` values used as examples in tracked
documentation and code — resolves to a rule in a committed `.gitignore`; no tracked file
is shadowed by those ignore rules, so every tracked file stays trackable; and no tracked
file carries a real tenant identifier, UPN, email address, `onmicrosoft` host or
non-placeholder GUID. It is a heuristic gate over this repository only: it reduces, and
never replaces, the pre-push privacy audit, and it says nothing about a path written
outside the working tree. Both checks run in CI and exit `1` with the offending path on
drift. Sinks and retention are documented in
[docs/IDENTITY_AND_RETENTION.md](./docs/IDENTITY_AND_RETENTION.md).

### 🚦 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Assessment completed |
| `1` | Assessment failed (collection, normalization, configuration) |
| `2` | Completed with blocking findings, `--fail-on-blocking` set |
| `3` | Completed but preceptorship escalated, `--fail-on-review` set |

Codes 2 and 3 are pipeline signals, not crashes: a CI gate can tell "the tool broke"
from "the tenant is not ready" without parsing output.

> [!TIP]
> `--fail-on-blocking` is available for a deployment-owned CI or scheduler integration.
> This repository does not yet include a versioned recurrence artifact or evidence of
> two unattended runs; until that Phase 5 gate is met, the pipeline is **schedulable**,
> not **scheduled**.

---

## 🔎 Reading the Results

A run prints score, status, coverage and confidence together, then its blocking findings,
then the backlog. Read it in that order — **blocking findings first**, `NOT_EVALUATED`
second (a blind spot to fix by collecting more evidence, never by re-scoring), scores
third and always beside their confidence, backlog last.

[docs/INTERPRETING_RESULTS.md](./docs/INTERPRETING_RESULTS.md) is the operator's guide:
what each console column means, a triage table from result pattern to first move, why an
over-broad AI data schema scores worse than a scoped one, why agent instructions do not
fix a model-metadata problem, and why "Approved for Copilot" never moves a score here.
The console points at the same guide, so nothing in this repository depends on loading an
agent Skill to interpret a run.

The normative thresholds live in [docs/SCORING.md](./docs/SCORING.md); the rule detail
lives in [docs/RULES.md](./docs/RULES.md).

---

## 🚀 Deploy To Fabric

The whole assessment also ships as a native Fabric solution — a Lakehouse, a notebook
and a Data Pipeline — so it can be triggered inside the estate it evaluates instead of
only from someone's laptop. Recurrence, identity, overlap prevention, notifications,
and retention remain deployment-owned scheduling work.

```powershell
$env:FABRIC_TOKEN  = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$env:ONELAKE_TOKEN = az account get-access-token --resource "https://storage.azure.com" --query accessToken -o tsv

python fabric\deploy.py --workspace-id <workspace-guid> --tenant-id <entra-tenant-guid>
```

The deployment is idempotent: items are looked up by display name and updated, never
duplicated. The `fabric_iq` package is uploaded as plain sources to `Files/lib` on the
Lakehouse — no wheel, no `%pip install`, because it is standard library only.

Results land in the `FabricIQReadiness` Lakehouse: the medallion layers under
`Files/readiness/`, the HTML report, and the nine Gold marts published as Delta tables
ready for the DirectLake governance semantic model. Deployment also sets the workspace
Spark runtime to **2.0** by default (pass `--skip-spark-runtime-upgrade` to leave it
unchanged).

By default the notebook publishes the DirectLake Delta marts in snapshot mode
(`delta_publish_mode = "overwrite"`), so the report shows the latest readiness run
without duplicate historical rows. The medallion JSONL files still preserve every run;
switch `delta_publish_mode` to `"append"` only for explicit trend experiments.

Full instructions, prerequisites and caveats: [`fabric/README.md`](fabric/README.md).

### 📦 One-Notebook Install (Recommended)

The easiest way to get the whole solution into a workspace: import a single notebook
from GitHub, run it, done. No local Python, no `az` CLI, no service principal.

1. In the target Fabric workspace: **New item ▸ Notebook ▸ Import notebook**, and
   import `fabric/items/Install_IsFabricReadyForIQ.Notebook/notebook-content.py` from
   [github.com/cyphou/FIQA](https://github.com/cyphou/FIQA) (raw file URL).
2. Open the imported notebook, adjust the parameters cell if needed (defaults deploy
   into the current workspace using the `main` branch), and **Run all**.
3. It downloads the public source over plain HTTPS, deploys the five items using
   **your own** delegated Fabric identity (`notebookutils.credentials.getToken` —
   no secrets, ever), and cleans up its temp files.

Full walkthrough, parameter reference and the confidentiality guarantees this notebook
upholds: [docs/INSTALL.md](docs/INSTALL.md).

> [!NOTE]
> The installer never stores a secret. It only ever holds the delegated bearer token
> `notebookutils.credentials.getToken(...)` hands it, in memory, for the run's duration.

---

## 📊 Power BI Report

`assess.py --powerbi <folder>` generates a hand-authored `.pbip` project styled after
the FUAM / Fabric Capacity Metrics visual language: a dark KPI band, status-colored
donut and bar visuals, and a scorecard-detail matrix — built from the run's scorecards,
findings and remediation backlog, with no live connection to your tenant.

```bash
python assess.py --inventory examples/sample_tenant --powerbi ./powerbi_report
```

This writes a self-contained project you open directly in Power BI Desktop:

```
powerbi_report/
├── IsFabricReadyForIQ.pbip
├── IsFabricReadyForIQ.Report/       # report.json (pages/visuals) + report.config.json
├── IsFabricReadyForIQ.SemanticModel/  # model.bim (import-mode TMSL)
├── data/                            # CSV sources: scorecards, findings, backlog
├── FabricIQ_Theme.json              # optional — apply via View ▸ Themes ▸ Browse
└── README.md
```

> [!WARNING]
> The generated folder is **evidence, not source**. `powerbi_report/data/*.csv` carries
> workspace, object and finding names from the assessed tenant, so `powerbi_report/` is
> git-ignored and must never be committed. Treat the output like any other assessment
> artifact: share it under the same handling rules as the tenant data it describes.
> `python scripts/check_evidence_sinks.py` enforces that this ignore rule stays
> committed, instead of leaving the guarantee to this paragraph.

Constraints: the semantic model's CSV partitions reference **absolute file paths**
generated at write time, so re-open the `.pbip` from the same machine (or update the
paths in Power BI Desktop) after moving the folder. The theme is not auto-applied by
Desktop and must be browsed in manually. Because this environment cannot open Power BI
Desktop, the JSON structure is validated (schema shape, page/visual counts, CSV row
parity with the run) but the visual rendering itself is unverified.

---

## 📚 Rule Catalogue

65 rules, ruleset version `2026.09.1`.

| Object | Rules | Blocking | Prefix |
|--------|-------|----------|--------|
| Tenant | 12 | 4 | `TEN-` |
| Workspace | 11 | 4 | `WKS-` |
| Semantic model | 17 | 5 | `SEM-` |
| Report | 10 | 1 | `REP-` |
| Data Agent | 15 | 10 | `AGT-` |

See [docs/RULES.md](./docs/RULES.md) for the full catalogue.

---

## 🧮 Scoring Contract

- A **blocking** failure caps the score at **39** and revokes eligibility.
- A **major** failure caps the score at **59**.
- A cap only ever lowers a score, never raises one.
- Missing evidence yields `NOT_EVALUATED` — never a pass, never a zero.
- Coverage below **50%** publishes `NOT_EVALUATED` instead of a score.
- Dimension weights are renormalized over observed dimensions, so an unobservable
  dimension lowers **confidence**, not **score**.

| Score | Status |
|-------|--------|
| ≥ 85 | READY |
| ≥ 70 | READY_WITH_CONDITIONS |
| ≥ 50 | REMEDIATION_REQUIRED |
| < 50 | NOT_READY |

Details in [docs/SCORING.md](./docs/SCORING.md).

---

## 🏗️ Architecture

```
Fabric / Power BI APIs → [Collect] → Bronze evidence
                                   → [Normalize] → Silver inventory
                                   → [Score] → Scorecards + Findings
                                   → [Prioritize] → Remediation backlog
                                   → [Review] → Preceptorship verdict
                                   → [Persist] → Lakehouse Gold marts
```

Nine Gold marts feed a DirectLake readiness semantic model and report:

`MartRunSummary`, `MartTenantReadiness`, `MartWorkspaceReadiness`, `MartObjectReadiness`,
`MartBlockingFindings`, `MartRemediationBacklog`, `MartRemediationBurnDown`,
`MartCoverageAndFreshness`, `MartRunTrend`.
`MartRunTrend` is populated automatically from the latest previous comparable run in
the medallion report history; the first run stays empty but schema-stable.
`MartRemediationBurnDown` uses the same comparable history to classify backlog work as
`new`, `open`, `resolved`, `reopened` or `changed_priority`.
The model keeps those PascalCase names for business readability, while its DirectLake
partitions point to the Lakehouse SQL endpoint's physical lowercase table names
(`marttenantreadiness`, `martobjectreadiness`, and so on). This keeps the model
AI-readable without breaking table resolution in Fabric.

See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md).

The readiness semantic model/report also pass their own executable gate:
[docs/SELF_ASSESSMENT.md](./docs/SELF_ASSESSMENT.md) records the result and
`tests/test_self_assessment.py` keeps the ≥85 score / ≥90% confidence+coverage threshold
from drifting.

The same assessment package is invoked locally through `assess.py` and inside Fabric
through the notebook in [`fabric/items/`](./fabric/items). This provides one
implementation for both paths; it is not evidence that unattended runs or a two-run
re-measurement cadence have completed.

---

## 🤖 Multi-Agent Environment

The repository ships a 14-agent environment under [.github/agents/](./.github/agents).
Twelve agents own a declared set of files; ownership drift fails the build. Two own
nothing by design — `@change-preceptor`, which reviews changes, and `@security`, which
audits privacy.

| Agent | Owns |
|-------|------|
| 🎼 `@orchestrator` | End-to-end run, CLI surface, exit codes — the **tech lead** that plans and assigns |
| 🔎 `@collector` | Evidence acquisition, Silver inventory normalization |
| 🧮 `@scorer` | Scoring engine, dimension weights, rule registry |
| 🏢 `@tenant` | Tenant & workspace-level rules |
| 📐 `@semantic` | Semantic model & report rules |
| 🕵️ `@dataagent` | Fabric Data Agent readiness rules |
| 🎓 `@preceptor` | Reviews the assessment itself — the preceptorship loop |
| 🧑‍🏫 `@change-preceptor` | Reviews a **code change** before it lands — nothing, by design |
| 🛠️ `@remediation` | Backlog prioritization, owner routing |
| 🏛️ `@lakehouse` | Gold marts, persistence, Power BI model & report |
| 🧪 `@tester` | Fixtures, regression coverage, ownership enforcement |
| 📖 `@readme` | Documentation accuracy |
| 🗺️ `@roadmap-planner` | Phase sequencing, release gates |
| 🔐 `@security` | Privacy, least-privilege, secret handling |

### 🧑‍🏫 Two Roles of Oversight

Development work runs a **Plan → Assign → Implement → Review** loop with two separate
overseers: `@orchestrator` plans and assigns, the owning specialist implements, and
`@change-preceptor` reviews the change before it lands and coaches the owner rather
than fixing the code. It owns no file, so it never approves its own work.

> [!IMPORTANT]
> Two agents carry the word *preceptor* and they are not the same role.
> `@preceptor` reviews the **assessment** a run produced — a product feature you can
> invoke with `--review`. `@change-preceptor` reviews a **code change** to this
> repository and ships no code at all.

### 🔁 The Preceptorship Loop (`@preceptor`)

`@preceptor` reviews the **assessment itself**, not the tenant:

```
DRAFT (run) → REVIEW (@preceptor) → APPROVE? (≥ 4★?)
     ↑                                 │
     │            YES ─────────────────→ PUBLISH
     │             NO ─────────────────→ COACH
     │                                   │
     └───────────────────────────────────┘
              (max 3 cycles, then escalate)
```

Six dimensions: evidence completeness, rule coverage, blocking integrity, remediation
actionability, score traceability, freshness. The failure mode it guards against is not
a wrong score — it is a *confident* score built on thin evidence, because that one gets
acted on.

See [docs/AGENTS.md](./docs/AGENTS.md).

---

## 🛡️ Safety Properties

- **Strictly read-only.** The tool never modifies a tenant, under any flag.
- **Synthetic fixtures only.** No tenant-derived data in the repository.
- **Auditable.** Every finding traces to a hashed, timestamped API payload.

---

## 📌 Status and Limits

The engine, rule catalogue, scoring, review loop and persistence run against offline
fixtures. Live collection supplies a stdlib-only, read-only foundation:
it accepts an injected bearer token, reads tenant settings and Scanner workspace
metadata, follows page links, backs off on `429`, and can resume from a checkpoint.
Use a token environment-variable name rather than placing a token on the command line:

```bash
FABRIC_ACCESS_TOKEN=... python assess.py --live --tenant-id <tenant-id> \
  --bearer-token-env FABRIC_ACCESS_TOKEN --checkpoint artifacts/live-checkpoint.json
```

The transport, Scanner normalisation, selected capacity fields, and both Fabric
pipeline gate branches have been exercised against a live tenant. Complete API/SKU
field coverage has **not** been established: Prep-for-AI, AI instructions, verified
answers, Data Agent definition/source fields, relationships, and some capacity signals
remain unconfirmed or unavailable. Static Data Agent rules can consume supplied
evidence, but this repository has no behavioural execution harness. See
[docs/KNOWN_LIMITATIONS.md](./docs/KNOWN_LIMITATIONS.md) before quoting any result as a
complete tenant or agent assessment.

Phase 5 is **Evidence Closure and Repeatable Re-Measurement**. It remains open until
the API reality matrix, rule/input reconciliation, dated product-fact verification,
practitioner calibration, real Data Agent execution proof, and two compatible
unattended runs satisfy the gates in [docs/ROADMAP.md](./docs/ROADMAP.md).

> [!WARNING]
> This tool never reports a score without eligibility and confidence alongside it —
> a high score at low confidence is a blind spot, not a passing grade.

Roadmap and release gates: [docs/ROADMAP.md](./docs/ROADMAP.md).

---

## 📜 License

Internal project. See repository settings.
