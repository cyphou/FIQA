# IsFabricReadyForIQ

Assess whether a Power BI / Microsoft Fabric tenant and its objects are ready for
**Fabric IQ** and agentic experiences.

For every object — tenant, workspace, semantic model, report, Fabric Data Agent — the
tool produces:

| Result | Question it answers |
|--------|--------------------|
| **Eligibility** | Does anything make this object structurally impossible to use? |
| **Readiness score** (0–100) | How well prepared is it, across weighted dimensions? |
| **Confidence** | How much of it could we actually observe? |
| **Remediation backlog** | What to change, who owns it, how long it takes |

These are **three separate results**. A high score with low confidence is a statement
about blind spots, not an endorsement — and the tool refuses to merge them into one
reassuring number.

## Why This Exists

The building blocks exist — Scanner APIs, Semantic Link Labs, the Fabric Data Agent SDK,
Microsoft's "prepare data for AI" guidance. What is missing is the layer that walks the
whole chain, from tenant switch to agent answer, and produces a consolidated, explainable
verdict with an owned remediation list. That is this project.

## Quick Start

```bash
# Score the synthetic sample tenant, with preceptorship review
python assess.py --inventory examples/sample_tenant --review --out artifacts

# Inspect the rule catalogue
python assess.py --list-rules

# Run the test suite
python -m unittest discover -s tests -t .

# Verify multi-agent file ownership
python scripts/check_agent_ownership.py
```

No dependencies. Python 3.12+ standard library only.

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Assessment completed |
| `1` | Assessment failed (collection, normalization, configuration) |
| `2` | Completed with blocking findings, `--fail-on-blocking` set |
| `3` | Completed but preceptorship escalated, `--fail-on-review` set |

Codes 2 and 3 are pipeline signals, not crashes: a CI gate can tell "the tool broke"
from "the tenant is not ready" without parsing output.

## Deploy To Fabric

The whole assessment also ships as a native Fabric solution — a Lakehouse, a notebook
and a Data Pipeline — so it can run on a schedule inside the estate it evaluates
instead of from someone's laptop.

```powershell
$env:FABRIC_TOKEN  = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$env:ONELAKE_TOKEN = az account get-access-token --resource "https://storage.azure.com" --query accessToken -o tsv

python fabric\deploy.py --workspace-id <workspace-guid> --tenant-id <entra-tenant-guid>
```

The deployment is idempotent: items are looked up by display name and updated, never
duplicated. The `fabric_iq` package is uploaded as plain sources to `Files/lib` on the
Lakehouse — no wheel, no `%pip install`, because it is standard library only.

Results land in the `FabricIQReadiness` Lakehouse: the medallion layers under
`Files/readiness/`, the HTML report, and the six Gold marts published as Delta tables
ready for a governance semantic model.

Full instructions, prerequisites and caveats: [`fabric/README.md`](fabric/README.md).

### One-Notebook Install (Recommended)

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

## Power BI Report

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

Constraints: the semantic model's CSV partitions reference **absolute file paths**
generated at write time, so re-open the `.pbip` from the same machine (or update the
paths in Power BI Desktop) after moving the folder. The theme is not auto-applied by
Desktop and must be browsed in manually. Because this environment cannot open Power BI
Desktop, the JSON structure is validated (schema shape, page/visual counts, CSV row
parity with the run) but the visual rendering itself is unverified.

## Rule Catalogue

62 rules, ruleset version `2026.09.1`.

| Object | Rules | Blocking | Prefix |
|--------|-------|----------|--------|
| Tenant | 10 | 4 | `TEN-` |
| Workspace | 10 | 4 | `WKS-` |
| Semantic model | 17 | 5 | `SEM-` |
| Report | 10 | 1 | `REP-` |
| Data Agent | 15 | 10 | `AGT-` |

See [docs/RULES.md](./docs/RULES.md) for the full catalogue.

## Scoring Contract

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

## Architecture

```
Fabric / Power BI APIs → [Collect] → Bronze evidence
                                   → [Normalize] → Silver inventory
                                   → [Score] → Scorecards + Findings
                                   → [Prioritize] → Remediation backlog
                                   → [Review] → Preceptorship verdict
                                   → [Persist] → Lakehouse Gold marts
```

Six Gold marts feed a readiness semantic model and report:
`MartTenantReadiness`, `MartWorkspaceReadiness`, `MartObjectReadiness`,
`MartBlockingFindings`, `MartRemediationBacklog`, `MartCoverageAndFreshness`.

See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md).

The same pipeline runs in two places: locally through `assess.py`, and inside Fabric
through the notebook in [`fabric/items/`](./fabric/items). Both call the identical
`fabric_iq` package, so a local run and a scheduled workspace run produce the same
scorecards.

## Multi-Agent Environment

The repository ships a 13-agent environment under [.github/agents/](./.github/agents).
Each agent owns a declared set of files; ownership drift fails the build.

`@orchestrator` `@collector` `@scorer` `@tenant` `@semantic` `@dataagent`
`@preceptor` `@remediation` `@lakehouse` `@tester` `@readme` `@roadmap-planner`
`@security`

### The Preceptorship Loop

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

## Safety Properties

- **Strictly read-only.** The tool never modifies a tenant, under any flag.
- **Synthetic fixtures only.** No tenant-derived data in the repository.
- **Auditable.** Every finding traces to a hashed, timestamped API payload.

## Status and Limits

The engine, rule catalogue, scoring, review loop and persistence run against offline
fixtures. Phase 1 also supplies a stdlib-only, read-only live collection foundation:
it accepts an injected bearer token, reads tenant settings and Scanner workspace
metadata, follows page links, backs off on `429`, and can resume from a checkpoint.
Use a token environment-variable name rather than placing a token on the command line:

```bash
FABRIC_ACCESS_TOKEN=... python assess.py --live --tenant-id <tenant-id> \
  --bearer-token-env FABRIC_ACCESS_TOKEN --checkpoint artifacts/live-checkpoint.json
```

Live API field coverage has not yet been verified against a tenant; see
[docs/KNOWN_LIMITATIONS.md](./docs/KNOWN_LIMITATIONS.md) before quoting any result as
a tenant assessment.

Roadmap and release gates: [docs/ROADMAP.md](./docs/ROADMAP.md).

## License

Internal project. See repository settings.
