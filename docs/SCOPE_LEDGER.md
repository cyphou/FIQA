# Scope Ledger

**What this document is.** A signed disposition for every element of Fabric's shape that
this repository already names in its own code. Today it covers **one** source —
`WORKSPACE_ITEM_KEYS` in [`fabric_iq/collectors/fabric_api.py`](../fabric_iq/collectors/fabric_api.py)
— and its **thirteen** item containers.

**Why it exists.** Before this document, the repository's scope read *identically*
whether an omission had been considered and rejected or had never been noticed at all.
That is how the ontology gap survived: the evidence was sitting in a constant the
collector maintains by hand, and nothing said whether its absence from the rule catalogue
was a decision. A verdict's scope should be something an owner signed, not a by-product of
which collector happened to be written first.

**What this document is not.**

- **It is not a detector.** A ledger is the baseline a detector needs. Closing Sprint 7.1
  closes nothing in Sprint 7.2, and **no criterion of the Phase 7 release gate is met at
  this revision.** Nothing here is checked by any script yet; `WORKSPACE_ITEM_KEYS` can
  gain a fourteenth key tomorrow and this document will not notice.
- **It is not a scoring input.** No row adds a rule, an `ObjectType`, a weight or a
  threshold. No row moves a score, a coverage figure or a confidence figure, and **no row
  is mapped to `NOT_EVALUATED`** — that outcome reports missing *evidence*, never an
  absent *rule*, and using it to express scope would trade a documented fact for a
  coverage loss.
- **It is not a statement that an excluded item type is unimportant.** An exclusion here
  says "this item type is not a subject this tool assesses, for the stated reason". It
  says nothing about its value to a tenant.
- **It does not enumerate Fabric.** Only what `WORKSPACE_ITEM_KEYS` already names is in
  scope of this revision. Finding item types the repository has never heard of is Sprint
  7.4's problem, not this document's.

**Covered sources, and the ones still unwritten.** `TENANT_SETTING_MAP` (6 settings) and
`ObjectType` (6 members, 5 with rules — `CAPACITY` carries none) are **not** covered here.
They are named so nobody reads this document as a complete scope statement.

---

## Disposition vocabulary

| Disposition | Means | Must carry |
|---|---|---|
| **assessed** | The engine reaches this item type and judges it | The rule IDs |
| **deliberately excluded** | Considered, and decided against | A reason, an owning agent, a review-by date |
| **open** | Intended, not done | The sprint that would close it |
| **untriaged** | Nobody has answered | The agent who must answer. **This disposition must be empty at the Phase 7 release gate. It is not empty today — four rows carry it.** |

**An exclusion reading "out of scope" with no reason is worse than silence, because it
looks decided.** A reasonless exclusion is a review finding, not a pass. Where a
defensible one-sentence reason could not be written, the row below says `untriaged` and
names the agent who owes the sentence — an honest empty is the finding, a confident
placeholder is the failure.

---

## The ledger — `WORKSPACE_ITEM_KEYS`, 13 rows

Reproduce the source list:

```bash
python -c "from fabric_iq.collectors.fabric_api import WORKSPACE_ITEM_KEYS as k; print(len(k)); print(list(k))"
# 13
```

Reproduce the rule counts behind every `assessed` row:

```bash
python assess.py --list-rules          # 67 rules, ruleset 2026.09.2
```

| # | Item key | Disposition | Basis | Owner | Review by |
|---|---|---|---|---|---|
| 1 | `reports` | **assessed** | `REP-001`–`REP-011` (11 rules, `ObjectType.REPORT`) | `@semantic` (`fabric_iq/rules/report_rules.py`) | n/a |
| 2 | `datasets` | **assessed** | `SEM-001`–`SEM-018` (18 rules, `ObjectType.SEMANTIC_MODEL`) | `@semantic` (`fabric_iq/rules/semantic_model_rules.py`) | n/a |
| 3 | `DataAgent` | **assessed** | `AGT-001`–`AGT-015` (15 rules, `ObjectType.DATA_AGENT`) | `@dataagent` (`fabric_iq/rules/data_agent_rules.py`) | n/a |
| 4 | `dashboards` | **open** | Sprint 6.2, then Phase 6 release-gate criterion 3 (type reachability) | `@scorer` (6.2 decision) | n/a — tracked by the sprint |
| 5 | `Ontology` | **open** | Sprint 6.3 — *Ontology as an Assessed Object Type (preview)* | `@collector` (read record), then `@scorer` | n/a — tracked by the sprint |
| 6 | `dataflows` | **deliberately excluded** | Not a grounding target for either GA consumption surface and not a documented data agent data source; its readiness effect reaches an answer only through the semantic model that consumes it, which is assessed | `@readme` | 2026-12-24 |
| 7 | `datamarts` | **deliberately excluded** | Same reachability basis as `dataflows`: a self-service store whose only documented path into an IQ answer is the semantic model it surfaces | `@readme` | 2026-12-24 |
| 8 | `Notebook` | **deliberately excluded** | Compute and authoring, not a queryable subject: no documented Fabric IQ surface grounds on a notebook and it appears in no documented data agent source list | `@readme` | 2026-12-24 |
| 9 | `SQLAnalyticsEndpoint` | **deliberately excluded** | A derived surface, not an authored item — every lakehouse provisions one automatically, so any readiness statement about it is a statement about its parent item (row 10) | `@readme` | 2026-12-24 |
| 10 | `Lakehouse` | **untriaged** | Documented Fabric data agent data source; nobody has decided whether agent *sources* are assessed subjects | **`@dataagent` must answer** | — |
| 11 | `KQLDatabase` | **untriaged** | Documented Fabric data agent data source; same unanswered question as row 10 | **`@dataagent` must answer** | — |
| 12 | `Eventhouse` | **untriaged** | Container of KQL databases; its disposition is the *grain* half of row 11's question and must not be decided separately | **`@dataagent` must answer** | — |
| 13 | `GraphModel` | **untriaged** | Graph is a documented data agent source **in preview**, and the key's correspondence to that item is unverified against a live scan | **`@dataagent`, with `@collector` on the key mapping** | — |

**Tally: 3 assessed, 2 open, 4 deliberately excluded, 4 untriaged.** Every key resolves to
exactly one disposition; none carries two.

---

## The rows that needed more than a line

### 4 — `dashboards`: open, not excluded

Both GA consumption surfaces document dashboards as ungroundable, and both statements were
re-verified against the live pages on 2026-09-25 (§ *Sources*). It would therefore be easy,
and wrong, to close this row as "excluded — the surfaces cannot read it". The repository has
already committed in writing to saying the opposite out loud: **Phase 6 release-gate
criterion 3** requires that "a paginated report or a dashboard is flagged as unreachable by
a GA surface **with every quality figure on its scorecard unchanged**". That criterion is
recorded as *open and blocked*, because `ScoringEngine.score_object` offers no outcome that
states a documented unreachability without either moving the score or costing coverage.

So the disposition is **open**, and the sprint that would close it is **Sprint 6.2** (the
per-surface verdict decision), after which a reachability rule family can exist. Marking
this row "excluded" would contradict a live release criterion and would quietly delete the
one dashboard fact the tool is best placed to report.

### 6 and 7 — `dataflows`, `datamarts`: excluded on reachability, not on importance

The exclusion rests on a sourced fact, not on a view about ETL: Cowork "grounds on Power BI
reports and the semantic models behind them" and not on "Fabric items that aren't Power BI
reports or semantic models"; Copilot Chat's supported set is likewise reports and semantic
models. Neither item type appears in the documented data agent source list. Where upstream
staleness does reach an answer, it is observable on the object the surface actually reads —
`SEM-016` scores semantic-model freshness against its declared SLA.

**This is not a claim that dataflow health is irrelevant.** It is a claim about the
*subject*: the assessed object is the model, not its producer. Whether a producer's refresh
state should become an input to a semantic-model rule is a rule-design question, and it
belongs to `@semantic` — it is routed below rather than settled here.

### 9 — `SQLAnalyticsEndpoint`: excluded as a duplicate subject

"Every lakehouse automatically provisions a SQL analytics endpoint when created — there's
nothing extra to set up" (verified 2026-09-25). Nobody authors one, nobody configures one
independently of its parent, and its tables are a T-SQL projection of the parent's Delta
tables. A ledger row that assessed it separately would count the same data twice. This
exclusion deliberately does **not** pre-empt row 10: if `@dataagent` rules lakehouses in
scope, the subject is still the lakehouse, and this row is re-opened only if a readiness
fact turns out to live on the endpoint and nowhere else.

### 10–13 — the asymmetry this ledger will not paper over

The repository assesses the **agent** (15 rules) and **none of its documented sources**.
The documented source list is "a warehouse, a lakehouse, a Power BI semantic model, a KQL
database, a mirrored database, or an ontology" (verified 2026-09-25), plus graph in preview
and Microsoft Graph. Of those, the semantic model *is* assessed — because it is also a
Power BI object with its own rules, not because anyone decided agent sources were in scope.

That decision has never been made. It is `@dataagent`'s to make, it is not a documentation
judgement, and manufacturing a one-sentence reason here would be exactly the failure this
document is supposed to prevent. Four rows therefore stay `untriaged`, which is the state
the Phase 7 release gate forbids — correctly, and it is why Phase 7 is not met.

**A correction, recorded because it was nearly written as fact.** A working assumption
held that `SQLAnalyticsEndpoint` was itself a documented data agent data source. It is
not: neither *Fabric data agent creation* nor *Create a Fabric data agent* names a SQL
analytics endpoint anywhere on the page (both read 2026-09-25). The row above rests on
the auto-provisioning fact instead.

---

## Questions routed, not decided

| # | Question | Routed to | Rows it settles |
|---|---|---|---|
| Q1 | Are Fabric data agent **data sources** assessed subjects in their own right, or is the agent the only assessed subject and its sources merely inputs? | `@dataagent` | 10, 11, 12, 13 |
| Q2 | If sources are in scope, at what **grain** — the eventhouse, or the KQL database inside it? | `@dataagent` | 11, 12 |
| Q3 | Does the Scanner key `GraphModel` correspond to the Fabric **graph** item, and is any of its metadata readable by a read-only caller? | `@collector` | 13 |
| Q4 | Should an upstream producer's refresh state become an input to a **semantic-model** rule, given that `SEM-016` currently reads freshness from the model alone? | `@semantic` | 6, 7 (does not change their disposition; may add a rule elsewhere) |

No question above is routed to `@tenant`: `WORKSPACE_ITEM_KEYS` contains no tenant-level
element. `TENANT_SETTING_MAP` is where `@tenant`'s dispositions will be owed, and that
source is not covered by this revision.

---

## Unassessed is not unseen

Worth stating so no reader over-reads the table: all thirteen containers, including the ten
that reach no rule, are counted into a workspace's `items_total`
(`fabric_iq/collectors/fabric_api.py`, `FabricApiCollector.normalize_workspace`). `WKS-009`
reads that total together with `items_scanned` to score **scan coverage** — how much of the
workspace the scan retrieved, never the quality of an ontology or a notebook. Where
`items_scanned` is absent the rule returns `NOT_EVALUATED` (missing evidence) rather than
scoring. An excluded item type is therefore still visible to the coverage arithmetic, and
still invisible to every quality statement the tool makes.

---

## Sources

Every fact this document leans on, with the page that states it and the date it was last
verified. Same discipline as [`KNOWN_LIMITATIONS.md` §8](KNOWN_LIMITATIONS.md#8-product-limits-age):
a public source and an exact date per fact, because product limits age.

| Statement relied on | Source | Verified |
|---|---|---|
| Cowork "grounds on Power BI reports and the semantic models behind them. It doesn't currently ground on Power BI dashboards, paginated (RDL) reports, share links, or other Fabric items like lakehouses or eventhouses" | [Fabric IQ in Microsoft 365 Copilot Cowork](https://learn.microsoft.com/fabric/iq/connectors/cowork-overview) | 2026-09-25, live page |
| Copilot Chat: "Unsupported content: Paginated reports (RDL), dashboards, and top-level apps aren't supported" | [Fabric IQ in Microsoft 365 Copilot Chat](https://learn.microsoft.com/fabric/iq/connectors/microsoft-365-copilot-overview) | 2026-09-25, live page |
| Data agent data sources: "A warehouse, a lakehouse, a Power BI semantic model, a KQL database, a mirrored database, or an ontology" | [Fabric data agent creation (concepts)](https://learn.microsoft.com/fabric/data-science/concept-data-agent) | 2026-09-25, live page |
| The same list, restated on the creation path; **no mention of a SQL analytics endpoint anywhere on either page** | [Create a Fabric data agent](https://learn.microsoft.com/fabric/data-science/how-to-create-data-agent) | 2026-09-25, live page |
| "Fabric Data Agent supports graph as a data source (preview)" | [What is graph in Microsoft Fabric?](https://learn.microsoft.com/fabric/graph/overview) | 2026-09-25, live page |
| "Every lakehouse automatically provisions a SQL analytics endpoint when created — there's nothing extra to set up" | [What is the SQL analytics endpoint for a lakehouse?](https://learn.microsoft.com/fabric/data-engineering/lakehouse-sql-analytics-endpoint) | 2026-09-25, live page |
| "An Eventhouse is a container that can hold multiple databases" | [Eventhouse overview](https://learn.microsoft.com/fabric/real-time-intelligence/eventhouse) | 2026-09-25, live page |

**A note on one source that moved.** The Power BI datamart overview path now redirects to a
data-modelling hub rather than to a datamart article. That is an observation about a URL,
**not** evidence of a product retirement, and row 7 does not rest on it. Retiring
dependencies are tracked in [`KNOWN_LIMITATIONS.md` §10](KNOWN_LIMITATIONS.md#10-retiring-dependencies);
no rule in ruleset `2026.09.2` depends on datamarts.

---

## Observed while writing this, and deliberately not made into rows

Two item types documented as data agent data sources — **warehouse** and **mirrored
database** — are not enumerated in `WORKSPACE_ITEM_KEYS` at all. They are recorded here as
an observation about the *source constant's* completeness, not as ledger rows: a ledger row
requires an element the repository already names, and reconciling this repository against
Fabric's actual item catalogue is Sprint 7.4's job. A future ledger row for either of them
depends on `@collector` adding the key first.

---

## Maintaining this document

- **Review cadence: 90 days**, matching the cadence proposed in Sprint 7.3. Every
  `deliberately excluded` row above carries **2026-12-24**.
- **There is no bulk re-dating command, and there must not be one.** Clearing a review
  costs one deliberate per-row edit with a recorded reason. That cost is the point: a
  guard people regenerate without reading is decoration.
- **A review that found nothing is still evidence** and is written down with its date and
  the sources consulted, otherwise the next reviewer cannot tell a checked row from an
  unchecked one.
- **Changing a disposition is an owner's act.** `@readme` owns this document's accuracy and
  its dated sourcing; it does not own the judgements in rows 10–13 and will not write them.

**Ownership.** This document is a collection-capability claim and is therefore a
`REQUIRED_DOCS` entry in `scripts/check_agent_ownership.py`, accountable to `@readme`.

| Last full review | Reviewer | Source covered |
|---|---|---|
| 2026-09-25 | `@readme` | `WORKSPACE_ITEM_KEYS` (13 of 13 rows) |
