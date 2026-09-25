# API Reality Matrix

What the collector could and could not read, field by field, from a live tenant.

> ## ⚠️ Exploratory read — **NOT Sprint 5.1 gate evidence**
>
> This matrix was produced by an **exploratory, read-only** observation. It does **not**
> satisfy the Sprint 5.1 gate in `docs/ROADMAP.md` and must never be cited as that
> gate's proof. Two prerequisites the gate names did not happen:
>
> - **No prior scope and retention approval.** The gate requires `@security` to review
>   scopes and retention *before* the proof runs. This run was authorised directly by
>   the user; the review happened afterwards.
> - **No read-only service principal.** The reads were issued under a **delegated,
>   interactive identity** carrying the operator's full privilege set — including every
>   write that person holds. Least privilege was never demonstrated, so no row here
>   evidences read-only enforcement.
>
> Citing this run as the 5.1 proof would be quoting a gate that did not run.
>
> **What survives the caveat.** The API reality recorded below stands. Field
> availability is a property of the endpoint, not of the identity's provenance, and an
> over-privileged identity can only ever *overstate* what a scoped one would read — so
> every `absent` and `permission-blocked` row is, if anything, conservative.
>
> **What the real 5.1 proof still requires.** A re-run under a read-only service
> principal whose scopes and evidence expiry `@security` approves first.

This document is a **claim about collection capability**: every row says what a read
surface returned, and what that means for the rules that consume it. It is owned by
`@collector`, because the day `fabric_iq/collectors/` gains or loses a surface is the
day this file becomes wrong.

Last observed: **2026-09-24**, ruleset `2026.09.1`, 65 rules.

**Last documentation check: 2026-09-25 — which is not an observation date and must never
be read as one.** On that day public Microsoft REST reference pages were read to name
*which* endpoint would carry the fields Sprint 6.1 asks about. **No tenant was called, no
payload was retained, no `BronzeRecord` was produced, and "Last observed" deliberately
does not move.** Everything that check produced is confined to §11, which is labelled as
documentation throughout; no row in §5 rests on it.

## 1. Scope — Read This Before Quoting Any Row

This matrix records **one tenant** observed through **one read surface** on **one day**.
It does not generalise.

- **One tenant, one identity, one set of grants.** That identity was delegated and
  over-privileged (see the caveat above). A different tenant, a different SKU, or a
  service principal with admin consent would reclassify many rows — most obviously
  every row currently marked `permission-blocked`.
- **Two endpoints were exercised, and only two.** The Scanner (`getInfo`), the Admin
  APIs, the XMLA endpoint, the item-definition APIs and the Activity Events API were
  **not called at all** in this proof. `absent` below therefore means *this surface does
  not carry the field*, never *Fabric does not expose the field*.
- **The transport under test was not `fabric_api.py`.** The reads were issued through an
  authenticated Fabric MCP server; the payloads were then assembled into a local
  inventory and scored through `OfflineCollector` (`collector_mode: offline` in the run
  record). This proof validates **field availability**, not the live HTTP client.
- **No SKU claim is made.** Capacity SKU was unreadable here (§4), so nothing in this
  document supports or denies an F2+/P1+ statement for any tenant.

Raw payloads stay under `artifacts/live/`, which is git-ignored and never committed. No
workspace name, object name, GUID, capacity id or tenant id appears in this file, by
design — see §9 for how each row is reproduced without them.

**Estate-size counts are stated as ratios, not literals.** The read surface attributes
this estate to a named organisation, so a literal workspace or item count would be an
estate-size disclosure about it, and a field-availability claim never needs one: "`null`
for 100% of workspaces returned" carries the full force of the finding, and
order-of-magnitude ("tens of workspaces, single-digit catalog items") carries the scale.
Counts that say nothing about estate size — rules evaluated, blocking findings, ruleset
size — stay literal.

## 2. Classification Vocabulary

Phase 5 fixes five classes. They are applied strictly, and scoped to the endpoints
actually exercised.

| Class | Means |
|-------|-------|
| `available` | Observed, non-null, on an exercised endpoint, and usable without inference |
| `partial` | Observed, but incomplete, subset-only, or usable only by inferring something the payload does not state |
| `absent` | The endpoint answered `200` and simply does not carry the field — or returns `null` for every record |
| `permission-blocked` | The only endpoint that could carry it needs a scope this identity does not hold; no `200` was obtained |
| `preview-only` | Availability is gated behind a preview feature |

Two disciplines apply to the table below.

- **`null` for every record is `absent`, not "observed and empty".** A present key holding
  `null` is a blind spot; `[]` or `""` is an assertion. The collector must never convert
  the first into the second.
- **`preview-only` is unused in this matrix.** Not one field in this proof produced
  evidence of a preview gate — a preview banner, a `preview` flag, or a feature-gated
  error. Classifying a field `preview-only` from the *absence* of data would be inventing
  a product fact, which rule 6 of the shared instructions forbids. The class stays
  defined and empty until a preview gate is actually observed.

## 3. Endpoints Exercised

| # | Surface | Call | HTTP | Returned |
|---|---------|------|------|----------|
| **A** | OneLake data plane | workspace listing | `200` | tens of workspaces |
| **B** | Fabric catalog | catalog search, `Type eq 'SemanticModel'` | `200` | single-digit items |
| **B** | Fabric catalog | catalog search, `Type eq 'Report'` | `200` | single-digit items |

Fields returned by **A**, per workspace: `id`, `displayName`, `type`,
`metadata.workspaceObjectId`, `metadata.regionalServiceEndpoint`,
`metadata.workspacePortalUrl`, `properties.lastModified`. Present but `null` for **100%
of workspaces returned**: `description`, `capacityId`, `defaultDatasetStorageFormat`.

Fields returned by **B**, per item: `id`, `type`, `displayName`, `description`,
`hierarchy.workspace.id`, `hierarchy.workspace.displayName`. Nothing else — no tables,
columns, measures, relationships, RLS, AI metadata, endorsement, refresh history or
lineage.

No other call produced a retained payload. In particular, **no tenant-admin endpoint
returned `200`** on this surface.

## 4. Two Findings That Change Collector Design

### 4.1 The two surfaces return disjoint workspace sets

Every workspace behind a catalog item is missing from the OneLake listing **by GUID and
by display name alike**: the intersection is **empty on both keys — 0% overlap on GUID,
0% on case-folded display name**. The union of the two surfaces is therefore their exact
sum, with no deduplication at all.

**Consequence.** A collector built on either surface alone silently omits the other —
and silently is the whole problem: it would report a complete-looking tenant while
missing **100% of the workspaces the other surface saw**, here, and an unknown share
elsewhere. Any future
multi-surface collector must union the surfaces on the GUID and record *which surface
saw each workspace*, so that a workspace observed by only one surface carries reduced
coverage rather than an unqualified presence.

### 4.2 On surface A, `id` is a name, not a GUID

**Every** workspace returned an `id` that is a **name string**: `0%` of `id` values are
GUID-shaped. The GUID is carried separately in `metadata.workspaceObjectId`, present on
**100% of workspaces returned**. A normalizer that keys on `id` by convention would key the inventory on a
mutable display name and cross-surface joins would fail without raising.

## 5. The Matrix

`Rule input` is the key a rule reads from its subject; `absent` inputs produce
`NOT_EVALUATED`, never a pass and never a zero.

### 5.1 Tenant

| Rule input | Rules | Surface | Outcome | Class | Consequence |
|---|---|---|---|---|---|
| `fabric_enabled` | TEN-001 | none exercised | no `200` | `permission-blocked` | Blocking rule unevaluable; tenant eligibility undecidable |
| `copilot_enabled`, `agents_enabled` | TEN-002 | none exercised | no `200` | `permission-blocked` | Blocking rule unevaluable |
| `copilot_security_groups` | TEN-003 | none exercised | no `200` | `permission-blocked` | Rollout scoping unassessed |
| `capacities` | TEN-004, TEN-005 | none exercised | no `200` | `permission-blocked` | No SKU, state or throttling statement is possible |
| `cross_geo_required`, `cross_geo_approved` | TEN-006 | none exercised | no `200` | `permission-blocked` | Blocking residency rule unevaluable |
| `scanner_enabled`, `scanner_service_principal` | TEN-007 | none exercised | no `200` | `permission-blocked` | Cannot confirm the tenant would even permit a Scanner run |
| `workspaces_total` | TEN-008 | A + B | `200` | `partial` | Only the **union** of two disjoint surfaces is credible; either alone undercounts |
| `workspaces_scanned` | TEN-008 | B | `200` | `partial` | Item-bearing workspaces are **under 10% of the union**; the run scored **partial** on that ratio |
| `sensitivity_labels_enabled`, `labelled_item_ratio` | TEN-009 | none exercised | no `200` | `permission-blocked` | No label posture |
| `audit_log_enabled`, `owners` | TEN-010 | none exercised | no `200` | `permission-blocked` | No accountability evidence |
| `copilot_capacity_designation_enabled` | TEN-011 | none exercised | no `200` | `permission-blocked` | — |
| `purview_dlp_reviewed` | TEN-012 | none exercised | no `200` | `permission-blocked` | — |
| *Share Fabric data with your Microsoft 365 services* — Fabric admin portal (no rule) | — | none exercised | no `200` | `permission-blocked` | Same cause as every `permission-blocked` row above: no tenant-admin endpoint answered. A future rule over this gate is **born `NOT_EVALUATED`**; the documented vendor default is not its value (§11.1) |
| *Fabric data available in M365 Copilot* — **Microsoft 365 admin center** (no rule) | — | A, B | `200` | `absent` | **A different control plane.** The two surfaces that answered carry no such setting, and no Fabric-side endpoint is documented to carry it either (§11.2). This is a **permanent blind spot** for one of the three Microsoft 365 gates, not a scope that could be widened |

TEN-008 is the **only rule in the entire 65-rule catalogue** that evaluated on this
evidence, and it evaluated to `partial`.

**Why the two Microsoft 365 rows carry different classes.** `permission-blocked` (§2)
presumes an endpoint exists that a wider scope would open. The Fabric-portal setting is a
Fabric tenant setting and would arrive with the rest of `/admin/tenantsettings` the day
that endpoint answers `200`, so it is blocked for exactly the reason `fabric_enabled` is.
The Microsoft 365 admin-center setting would not arrive with it: it is administered in
another control plane, and **a Fabric-scoped read-only principal has no route to it at
all**, so what remains is `absent` — the exercised surfaces answered `200` and do not
carry it. Neither row is `preview-only`: both settings are GA, and per §2 that class stays
empty until a preview gate is *observed*. Both rows are recorded on Sprint 6.1's stated
terms — a setting that cannot be read is `absent` or blocked, and its rule is born
`NOT_EVALUATED` rather than assumed from a documented default. The third Microsoft 365
gate, cross-geo AI processing, is already above as `cross_geo_required` /
`cross_geo_approved` (TEN-006) and is likewise unread.

### 5.2 Workspace identity and capacity

| Rule input | Rules | Surface | Outcome | Class | Consequence |
|---|---|---|---|---|---|
| workspace GUID (`metadata.workspaceObjectId`) | identity, all `WKS-*` joins | A | `200`, present on every workspace | `available` | Usable as the inventory key — **not** the `id` field (§4.2) |
| workspace display name | identity | A, B | `200` | `available` | Present on both surfaces; still not a join key |
| workspace `description` | identity | A | `200`, `null` for 100% | `absent` | Not observed; must stay unset, not `""` |
| `capacity_sku` | WKS-001, WKS-010, WKS-011 | A | `200`, `capacityId` `null` for **100%** of workspaces | `absent` | **Every `WKS-*` capacity rule is unevaluable**, including two blocking ones. The workspace→capacity join has no left-hand side on this surface |
| `capacity_state` | WKS-010 | A | `200`, `null` | `absent` | Blocking rule unevaluable |
| `copilot_capacity_assigned` | WKS-011 | A | `200`, `null` | `absent` | — |
| `business_owner`, `technical_owner` | WKS-002 | A, B | `200`, no such field | `absent` | Blocking ownership rule unevaluable |
| `role_assignments` | WKS-003, WKS-004 | A, B | `200`, no such field | `absent` | No permission posture; needs a Scanner call with user detail, not exercised here |
| `region` | WKS-006 | A | `200`, `metadata.regionalServiceEndpoint` on every workspace | `partial` | A service-endpoint host is **not** a capacity region. Mapping one to the other is inference and is deliberately not normalized |
| `source_regions`, `cross_geo_approved` | WKS-006 | none | — | `absent` | Blocking residency rule unevaluable regardless of `region` |
| `lifecycle_stage` | WKS-005 | A, B | `200`, no such field | `absent` | — |
| `days_since_last_activity` | WKS-007 | A | `200`, `properties.lastModified` on every workspace | `partial` | Metadata modification is not *activity*; treating it as activity would invent usage. Real activity needs the Activity Events API (1 UTC day/request, 28-day retention), not exercised |
| `refresh_total`, `refresh_failed` | WKS-008 | none | — | `absent` | No refresh history on either surface |
| `items_total`, `items_scanned`, `scan_errors` | WKS-009 | B | `200`, per-type only | `absent` | Catalog search is a tenant-wide query *per type*; counting it per workspace would report "items of the types I happened to ask for", not `items_total` |
| `defaultDatasetStorageFormat` (no rule) | — | A | `200`, `null` for 100% | `absent` | Recorded because it is the only storage hint on this surface, and it is empty |

### 5.3 Semantic model

| Rule input | Rules | Surface | Outcome | Class | Consequence |
|---|---|---|---|---|---|
| model id, display name, parent workspace | identity | B | `200`, on every item returned | `available` | Objects can be *enumerated*; nothing about them can be *judged* |
| model `description` | identity | B | `200`, non-empty on 60%, `""` on 40% | `partial` | Present as a key; no rule consumes the model-level description directly |
| `tables` | SEM-001, SEM-004, SEM-005, SEM-006 | B | `200`, no such field | `absent` | Structure rules unevaluable |
| `columns` | SEM-005, SEM-006, SEM-007, SEM-013 | B | `200`, no such field | `absent` | Metadata-quality rules unevaluable |
| `measures` | SEM-003, SEM-005, SEM-006, SEM-007, SEM-010, SEM-014 | B | `200`, no such field | `absent` | Includes blocking SEM-003 |
| `relationships` | SEM-001, SEM-002 | B | `200`, no such field | `absent` | Blocking SEM-002 unevaluable. A prior live run also established that the Scanner's `relations` carries artefact lineage, not model relationships (`docs/KNOWN_LIMITATIONS.md` §1.1) — that is **prior-run evidence, not reproduced here** |
| `has_time_intelligence` | SEM-004 | none | — | `absent` | — |
| `ai_data_schema`, `visible_object_count` | SEM-008, SEM-009 | B | `200`, no such field | `absent` | Prep-for-AI stays unconfirmed; both rules are blocking |
| `ai_instructions` | SEM-011 | B | `200`, no such field | `absent` | Stays unconfirmed — this surface cannot answer the question either way |
| `verified_answers` | SEM-012 | B | `200`, no such field | `absent` | Stays unconfirmed |
| `rls_required`, `rls_roles` | SEM-015 | B | `200`, no such field | `absent` | Blocking security rule unevaluable |
| `hours_since_refresh`, `freshness_sla_hours` | SEM-016 | B | `200`, no such field | `absent` | No refresh history on this surface |
| `schema_retrieval_error` | SEM-017 | B | not produced | `absent` | The collector sets this sentinel on the Scanner path only; on this surface there is no schema call to succeed or fail |
| item endorsement (`endorsement`, `endorsement_certified_by`) (no rule) | — | B | `200`, no such field | `absent` | §3 records the six fields surface B returns; endorsement is not among them. **No enumeration surface exercised in this proof returns endorsement.** Unchanged by the collector work of 2026-09-25: `fabric_api.py` now *carries* `endorsementDetails` on the **Scanner** path (§11.3), a surface this proof never called, so this row stays `absent` and "Last observed" does not move. What changed is the consequence of ever reaching that surface, not what was read here |

**All 17 `SEM-*` rules returned `NOT_EVALUATED`.** Catalog search enumerates semantic
models; it describes none of them.

### 5.4 Report

| Rule input | Rules | Surface | Outcome | Class | Consequence |
|---|---|---|---|---|---|
| report id, display name, parent workspace | identity | B | `200`, on every item returned | `available` | Enumeration only |
| report `description` | identity | B | `200`, non-empty on 25% | `partial` | — |
| `semantic_model_id`, `semantic_model_reachable` | REP-001 | B | `200`, no binding returned | `absent` | The catalog gives no report→model binding, so the **blocking** dependency rule cannot run |
| `semantic_model_score` | REP-002 | derived | — | `absent` | Injected by `fabric_iq/scoring.py` from the parent model's score, which is itself unpublishable at 0 confidence — a derived input cannot outrun its source |
| `visual_count`, `broken_visuals`, `untitled_visuals` | REP-003, REP-005, REP-007 | B | `200`, no such field | `absent` | Needs the report definition, not exercised |
| `report_level_measures` | REP-004 | B | — | `absent` | — |
| `hidden_filters` | REP-006 | B | — | `absent` | — |
| `visuals_with_alt_text` | REP-007 | B | — | `absent` | — |
| `audience`, `owner` | REP-008 | B | `200`, no such field | `absent` | — |
| `monthly_views` | REP-009 | none | — | `absent` | Activity Events API, not exercised |
| `verified_answer_candidates` | REP-010 | B | — | `absent` | — |
| item endorsement (`endorsement`, `endorsement_certified_by`) (no rule) | — | B | `200`, no such field | `absent` | Same finding as §5.3: surface B carries no endorsement for a report either (§3). Unread, not negative. The Scanner normalisation now carries it (§11.3) but the Scanner was not called here, so the class is unchanged |

### 5.5 Data Agent

| Rule input | Rules | Surface | Outcome | Class | Consequence |
|---|---|---|---|---|---|
| Data Agent item discovery | all `AGT-*` | B | no raw payload retained | `absent` *(asserted, not reproducible)* | The run recorded **zero** Data Agent items and the built inventory carries an empty list, but **no raw catalog response for an agent item type was kept**. The honest reading: the run asserts absence; this document cannot reproduce it from a payload. Re-run with the query retained before treating it as established |
| `data_sources` | AGT-001, AGT-002, AGT-005 | none | — | `absent` | Three rules, two blocking |
| `source_scores` | AGT-003 | none | — | `absent` | Blocking |
| `instructions` | AGT-004 | none | — | `absent` | — |
| `evaluation` | AGT-006 … AGT-012, AGT-014 | none | — | `absent` | Behavioural quality remains supplied-not-measured (`docs/KNOWN_LIMITATIONS.md` §3) |
| `target_languages` | AGT-012 | none | — | `absent` | Blocking |
| `requires_write`, `expects_bulk_export` | AGT-013 | none | — | `absent` | Blocking |
| `latency_sla_seconds` | AGT-014 | none | — | `absent` | — |
| `preview_dependencies` | AGT-015 | none | — | `absent` | — |

## 6. What The Run Did With This Evidence

The contracted degradation held exactly, and this is the part worth keeping:

| Observation | Value |
|---|---|
| Scorecards produced | one per inventory object — the tenant, every workspace in the union, every catalog item |
| Scorecard status | `NOT_EVALUATED` — **100% of scorecards** |
| Rules that evaluated | **1 of 65** — TEN-008, `partial`, scanned-workspace ratio under 10% |
| Tenant coverage / confidence | `0.10` / `0.00` — below the 50% coverage floor |
| Blocking findings | **0** — an unevaluable blocking rule is not a blocking failure |
| Preceptorship review | `escalated` at **2.34★** (evidence_completeness 1.0, rule_coverage 1.0, score_traceability 1.04, freshness 1.0, blocking_integrity 5.0, remediation_actionability 5.0) |
| CLI exit code | `3` under `--fail-on-review` |

Two of those numbers are the point of the whole exercise. **0 blocking findings** on a
tenant this unobserved is correct behaviour, not a clean bill of health: a rule that
could not run cannot fail. And a **2.34★ escalation** is the tool declining to publish
a verdict it cannot defend. Nothing in this run should be quoted as a readiness result
for the tenant; it is a result about the *surface*.

## 7. What This Proof Does **Not** Establish

Stated plainly, because a matrix that quietly overreaches is worse than no matrix.

1. **Nothing about the Scanner or Admin APIs.** They were not called. Every
   `permission-blocked` row is a statement about this identity on this surface.
2. **Nothing about other SKUs or other tenants.** Capacity was unreadable here, so no
   SKU-conditional behaviour was exercised at all.
3. **No negative product claim.** "AI instructions are `absent`" means the catalog search
   does not return them. It does **not** mean Fabric exposes no route to them.
4. **Three reported observations are not reproducible from the retained payloads** and
   are therefore excluded from the matrix rather than quietly included:
   a Lakehouse/Warehouse/Notebook catalog result, a `catalogEntryType` field on catalog
   items, and the Data Agent type query (§5.5). The retained files contain no payload for
   any of the three. A future proof must retain every query it wants to cite.
5. **Nothing about `fabric_api.py` in production.** The run's `collector_mode` is
   `offline`.
6. **Nothing about least privilege, and therefore nothing about the Sprint 5.1 gate.**
   The identity was delegated and interactive, holding the operator's full write
   privileges, and its scopes were never approved in advance. No row here shows what a
   read-only service principal would obtain, and no row may be quoted as 5.1 gate
   evidence — see the caveat at the top of this document.
7. **Nothing about the Microsoft 365 consumption gates or about endorsement was
   *observed*.** The two new §5.1 rows and the two endorsement rows say only what the
   exercised surfaces did not carry. §11 names the endpoints Microsoft *documents* as
   carrying these fields; that is a product claim read from a web page on 2026-09-25, not
   a tenant reading, and it evidences no field for any tenant.

## 8. Handoff To Sprint 5.2

Sprint 5.2 must select a field family *confirmed* here — but not on this evidence alone.
Sprint 5.1 is a hard prerequisite for 5.2 and this exploratory run did not clear it, so
the set below is a **provisional shortlist to re-confirm** under the approved identity,
not a cleared dependency. On this evidence the confirmed set is small and honest:

- **Confirmed `available`:** workspace GUID, workspace display name, catalog item id,
  item display name, item type, parent-workspace reference.
- **Confirmed `partial`:** workspace count (union only), scanned-workspace count, item
  descriptions, workspace region hint, workspace last-modified.
- **Everything else on this surface is `absent` or `permission-blocked`** and must keep
  returning `NOT_EVALUATED` until a *different* surface is proven — not until someone
  finds a plausible default.

The highest-value next proof is the one that unblocks the most blocking rules:
tenant settings and `/admin/capacities`, which together gate TEN-001, TEN-002, TEN-004,
TEN-006, WKS-001 and WKS-010.

## 9. Reproducing Every Row Without Committing Anything

The raw payloads live under `artifacts/live/` (git-ignored: `artifacts/` is an ignored
sink, asserted by `scripts/check_evidence_sinks.py`). Re-issue the two read-only calls,
keep the responses there, and the checks below reproduce every claim in §3 and §4
without a single identifier — or a literal estate size — leaving the machine. Each one
is a ratio against a denominator computed from the payload itself, so no count needs to
be written down here to verify it.

| Claim | How it is checked |
|---|---|
| Tens of workspaces on surface A | length of `results.workspaces` — the denominator for every ratio below |
| `capacityId` `null` for 100% of workspaces | count of entries whose `capacityId` is `None`, compared with that length — expect equality |
| `id` is never GUID-shaped | count of `id` values matching a 36-char, 4-dash shape — expect `0` |
| Single-digit catalog items per type | length of `results.results.value` per type query |
| Disjoint surfaces | intersection of workspace GUIDs, and of case-folded display names — expect `0` for both |
| Union loses nothing to deduplication | size of the union of those GUID sets — expect the sum of the two lengths |
| One scorecard per inventory object, 0 blocking, 1 rule evaluated | the run's assessment JSON, under `artifacts/live/` |
| 2.34★ escalation | the run's review JSON, `cycles[-1].average` and `verdict` |

Re-scoring the assembled inventory is the ordinary offline path:

```bash
python assess.py --inventory <local inventory dir> --review --fail-on-review --out artifacts/live
```

Keep the inventory directory outside version control. Fixtures under
`examples/sample_tenant/` are synthetic and must stay that way — a fixture captured from
a live run is a data leak waiting for a commit.

## 10. Ownership

Owned by `@collector`. It asserts what collection can and cannot acquire, so it goes
stale the moment a collector gains an endpoint — and the agent that would change the
endpoint is the agent that must change this file.

Related documents, owned elsewhere and updated by routing, never by editing:

- `docs/KNOWN_LIMITATIONS.md` §1 and §2 (`@readme`) — the standing statement that
  metadata availability is unconfirmed; §2's table is narrowed, not closed, by this proof.
- `README.md` (`@readme`) — any bounded claim about what a live run observes.
- `docs/ROADMAP.md` (`@roadmap-planner`) — the Sprint 5.1 gate this document does
  **not** satisfy. The caveat at the top is the reconciliation until a service-principal
  re-run exists; no roadmap entry may mark 5.1 cleared on this file.
- `scripts/check_agent_ownership.py` (`@tester`) — `REQUIRED_DOCS` must gain an entry for
  this file, mapped to `collector`, so the claim cannot go unowned.

## 11. Appendix — Documented Targets for Sprint 6.1 (**Checked 2026-09-25, Not Observed**)

> **Read this paragraph before quoting anything below.** Sections 1–10 record what a read
> surface *returned*. This section records what Microsoft's public reference pages *say*,
> read on **2026-09-25**, with **no API call of any kind made** — no tenant, no fixture,
> no `BronzeRecord`, no retained payload. It exists because Sprint 6.1 asks *which*
> endpoint would carry three fields, and naming an endpoint is a documentation question.
> It is forward-looking content on the same footing as §8, and it is **not evidence**:
> product documentation states what a product is designed to do, never what a tenant is
> configured to do or what a given identity may read. No sentence below may be quoted as
> "we read this", and nothing here changes a class in §5.

### 11.1 *Share Fabric data with your Microsoft 365 services* — the endpoint is known, the `settingName` is **not**

- **The endpoint is one this project already calls.** `GET
  https://api.fabric.microsoft.com/v1/admin/tenantsettings` (Admin API v1) returns the
  tenant settings list; the caller must be a Fabric administrator or authenticate as a
  service principal, with delegated scope `Tenant.Read.All` or `Tenant.ReadWrite.All`.
  The documented limit is **25 requests per minute**, with `429` carrying `Retry-After`
  ([reference](https://learn.microsoft.com/en-us/rest/api/fabric/admin/tenants/list-tenant-settings),
  checked 2026-09-25). `fabric_iq/collectors/fabric_api.py` already issues exactly this
  `GET` as its `tenant-settings` read, so **no new endpoint would be needed** — only a
  key to read out of the response.
- **The response shape is documented.** Each entry carries `settingName`, `title`,
  `enabled`, `canSpecifySecurityGroups`, `enabledSecurityGroups`,
  `excludedSecurityGroups`, `delegateToCapacity`, `delegateToDomain`,
  `delegateToWorkspace`, `properties` and `tenantSettingGroup` (same page, 2026-09-25).
- **The setting exists in the portal, under that exact title.** The Fabric tenant
  settings index lists a group *Share data with your Microsoft 365 services* containing
  the setting *Share Fabric data with your Microsoft 365 services*
  ([index](https://learn.microsoft.com/en-us/fabric/admin/tenant-settings-index), checked
  2026-09-25).
- **What is *not* established, and is therefore not written down as a fact.** That index
  page carries no API names at all, and the REST reference enumerates only three example
  `settingName` values — `AdminApisIncludeDetailedMetadata`, `DatamartTenant`,
  `CertifyDatasets` — none of which is this setting. **The `settingName` for *Share Fabric
  data with your Microsoft 365 services* is not established from public reference on
  2026-09-25.** It is consequently absent from this document and **not** wired into
  `TENANT_SETTING_MAP`: a guessed key does not fail loudly, it reads as an absent setting
  forever, which is precisely the silent gap this file exists to prevent. For the same
  reason it is **not established that the setting is returned by that endpoint at all** —
  the reference does not claim to enumerate the catalogue. Both questions are answered by
  one live `GET` under Sprint 5.1's approved identity, and that call has not been made.
- **The documented default, recorded only so that nobody substitutes it for a reading.**
  The index page states the setting "is automatically enabled only if your Microsoft
  Fabric and Microsoft 365 tenants are in the same geographical region" and that an admin
  may disable it (2026-09-25). That is a vendor default. Sprint 6.1's release gate, and
  §2 of this document, forbid it standing in for an observed value; the §5.1 row stays
  `permission-blocked`.

### 11.2 *Fabric data available in M365 Copilot* — another control plane, and a permanent blind spot

- **Where it lives.** Microsoft documents three tenant settings gating Power BI data in
  Microsoft 365 Copilot Chat: one in the **Microsoft 365 admin center** — *Fabric data
  available in M365 Copilot*, enabled by default, and when an admin turns it off users
  don't see Fabric context in Copilot responses — and two in the Fabric admin portal
  ([connector overview](https://learn.microsoft.com/en-us/fabric/iq/connectors/microsoft-365-copilot-overview),
  checked 2026-09-25).
- **No Fabric-side read surface is documented for it.** The Fabric admin tenant-settings
  reference (§11.1) covers Fabric tenant settings; nothing on it exposes a Microsoft 365
  admin-center control. On the Microsoft Graph side, the beta `copilotAdminSetting`
  resource exposes exactly one relationship — `limitedMode`, about sentiment prompts in
  Teams meetings — and mentions Fabric nowhere
  ([resource](https://learn.microsoft.com/en-us/graph/api/resources/copilotadminsetting?view=graph-rest-beta),
  checked 2026-09-25). **No public read surface for this gate was established on
  2026-09-25, in Fabric or in Graph beta.**
- **Stated plainly, because Sprint 6.1 asked for it plainly.** A Fabric-scoped read-only
  principal has no reason and no route to read a Microsoft 365 admin-center setting, and
  **no Fabric surface exposes it**. For this tool that gate is a **permanent blind spot**
  — permanent in the sense that no widening of Fabric scope reaches it. Closing it would
  require a Microsoft 365 control-plane read, separately scoped and approved by
  `@security`, which is outside Sprint 6.1 and outside this project's current grant. Any
  rule written over this gate is **born `NOT_EVALUATED` and stays there**, and its
  documented "enabled by default" is never its value.

### 11.3 Endorsement — absent from every exercised surface, documented on the Scanner

- **The observation, already on record.** §3 lists the six fields surface B returns per
  item and states that endorsement is not among them. That is the whole answer to Sprint
  6.1's third question: **no enumeration surface exercised in this proof returns item
  endorsement**, for semantic models or for reports. §5.3 and §5.4 now carry it as
  `absent`. Nothing was re-derived to say so.
- **The documented carrier.** The Scanner result — `GET
  https://api.powerbi.com/v1.0/myorg/admin/workspaces/scanResult/{scanId}` — documents an
  `endorsementDetails` object on reports, datasets (semantic models), dataflows and
  datamarts, whose fields are `endorsement` (string, "The endorsement status") and
  `certifiedBy` (string)
  ([reference](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result),
  checked 2026-09-25).
- **Three nuances that must survive into whatever rule is written later.**
  1. The reference types `endorsement` as a plain **string** and **does not enumerate its
     allowed values**; only the sample value `"Certified"` appears anywhere on the page.
     **The value set is not established from public reference on 2026-09-25**, so a rule
     must not hardcode one and a normalizer must not reject an unrecognised value.
  2. No documented `getInfo` parameter gates it. The documented query parameters are
     `lineage`, `datasourceDetails`, `datasetSchema`, `datasetExpressions` and
     `getArtifactUsers`, and only `datasetSchema` / `datasetExpressions` are documented as
     requiring metadata scanning to be fully enabled
     ([reference](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-post-workspace-info),
     checked 2026-09-25 — the same page restates the 500 requests/hour, 16 simultaneous
     requests and 1–100 workspace IDs limits this collector already encodes). Whether an
     unset tenant setting suppresses endorsement regardless is **not established**.
  3. **"Endorsement is admin-readable" is surface-specific, not general.** The Fabric
     admin item enumeration documents `id`, `type`, `name`, `description`, `state`,
     `lastUpdatedDate`, `workspaceId`, `capacityId`, `creatorPrincipal` and `tags`, with
     **no endorsement field**
     ([reference](https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-items),
     checked 2026-09-25), and the Power BI admin dataset enumeration reference does not
     mention endorsement at all
     ([reference](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/datasets-get-datasets-as-admin),
     checked 2026-09-25). Picking the wrong enumeration surface would produce a
     confident, permanent `absent`.
- The Scanner was **not called** in this proof (§1, §7.1). Nothing above is an
  availability claim for this tenant, this identity, or this collector.

#### 11.3.1 What absence means — the question the collector boundary had to settle

The `@collector` boundary §11.5 deferred was taken on **2026-09-25** (documentation
check, still **no live call**). It turns on one question: when `endorsementDetails` is
missing from an item in a successful scan, is that *"not endorsed"* or *"not read"*?

- **The reference settles it toward "not read".** Both the **Report** and the **Dataset**
  objects introduce their property list with: *"The API returns a **subset** of the
  following list of … properties. The subset depends on the API called, caller
  permissions, and the availability of data in the Power BI database."*
  ([reference](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result),
  checked 2026-09-25). An omitted property is therefore documented as a possible
  permission or availability artefact. **The page nowhere states how a non-endorsed item
  is represented** — neither "the object is omitted" nor "`endorsement` comes back empty".
- **So the distinction remains unresolved from public reference, and the collector
  defaults to the safe side.** Absent key, `null` container, empty container, `null`
  value, and any undocumented shape all normalise to `None` → `NOT_EVALUATED`. This is
  §2 applied, not restated: a present key holding `null` is a blind spot. Only an
  `endorsement` the service actually returned as `""` is carried as `""`, because an
  empty string is the service's own assertion.
- **What would settle it.** A single live Scanner `getInfo` + `scanResult` over a
  workspace containing one endorsed and one known-unendorsed item, under an identity with
  `Tenant.Read.All`. If the unendorsed item comes back **with** `endorsementDetails` and
  an empty or absent `endorsement`, absence-of-the-container remains a permission signal
  and the current mapping is right. If it comes back **without** the container at all,
  absence becomes ambiguous between the two causes and the rule must still degrade. That
  observation is blocked behind Sprint 5.1 and is **not** scheduled by this change.
- **No `getInfo` parameter was added.** The `getInfo` reference documents exactly five
  query parameters — `datasetExpressions`, `datasetSchema`, `datasourceDetails`,
  `getArtifactUsers`, `lineage` — and the word "endorsement" **does not appear on the
  page at all** (checked 2026-09-25). Nothing is known to gate endorsement the way
  `datasetSchema` gates schema, so `SCANNER_OPTIONS` is unchanged; a test pins that set
  so a future option cannot be invented silently.
- **No enum was introduced.** `Promoted` appears **zero** times on the scan-result
  reference; only the sample `"Certified"` appears, against a field typed `string —
  "The endorsement status"`. The product concept page meanwhile documents *three* portal
  levels — Promoted, Certified and Master data
  ([reference](https://learn.microsoft.com/en-us/fabric/governance/endorsement-overview),
  checked 2026-09-25) — and names no API field, which is precisely why the sample value
  must not be mistaken for the value set. The collector passes the string through as
  returned, stripping surrounding whitespace and nothing else.

#### 11.3.2 What the collector now carries — which is not the same as observed

`fabric_api.py` maps `endorsementDetails` onto two fields, `endorsement` and
`endorsement_certified_by`, on the Scanner's **dataset** (semantic model) and **report**
objects. The two fields are independent: a certifier can be stated without a status, and
carrying one never manufactures the other. `normalize_data_agent` lists both as
explicitly unavailable, because the reference documents `endorsementDetails` on reports,
datasets, dataflows and datamarts only — never on a Fabric item type. **Named as unknown
beats silently dropped**: the old `normalize_report` neither read the field nor listed
it, which is why this gap survived until a documentation review found it.

**This does not make endorsement observed.** §5.3 and §5.4 stay `absent`, "Last observed"
stays **2026-09-24**, and no `BronzeRecord` for a Scanner call exists. The only change is
that *if* the Scanner surface is ever reached, endorsement will arrive instead of
vanishing. **No rule consumes these fields** — that remains `@semantic`'s boundary.

### 11.4 Every source, with the date it was checked

| # | Claim it supports | Source | Checked |
|---|---|---|---|
| 1 | Tenant-settings endpoint, permissions, 25 req/min limit, response shape, three example `settingName` values | `https://learn.microsoft.com/en-us/rest/api/fabric/admin/tenants/list-tenant-settings` | 2026-09-25 |
| 2 | *Share Fabric data with your Microsoft 365 services* exists in the Fabric admin portal, its group, its description and its regional default; the page carries no API names | `https://learn.microsoft.com/en-us/fabric/admin/tenant-settings-index` | 2026-09-25 |
| 3 | Three gating settings, one of them in the Microsoft 365 admin center and enabled by default | `https://learn.microsoft.com/en-us/fabric/iq/connectors/microsoft-365-copilot-overview` | 2026-09-25 |
| 4 | Graph beta `copilotAdminSetting` exposes only `limitedMode` and names no Fabric control | `https://learn.microsoft.com/en-us/graph/api/resources/copilotadminsetting?view=graph-rest-beta` | 2026-09-25 |
| 5 | Scanner scan result documents `endorsementDetails` (`endorsement`, `certifiedBy`) on reports, datasets, dataflows, datamarts; `endorsement` is an unenumerated string | `https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result` | 2026-09-25 |
| 6 | `getInfo` parameters and quotas; only schema/expressions require metadata scanning | `https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-post-workspace-info` | 2026-09-25 |
| 7 | Fabric admin item enumeration carries no endorsement field | `https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-items` | 2026-09-25 |
| 8 | Power BI admin dataset enumeration reference does not document endorsement | `https://learn.microsoft.com/en-us/rest/api/power-bi/admin/datasets-get-datasets-as-admin` | 2026-09-25 |
| 9 | Report and Dataset scan-result properties are a *subset* depending on "the API called, caller permissions, and the availability of data in the Power BI database" — so an omitted `endorsementDetails` is documented as possibly unread, and the page never states how a non-endorsed item is represented (§11.3.1) | `https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result` | 2026-09-25 |
| 10 | The product documents three endorsement levels (Promoted, Certified, Master data) and names **no** API field — portal vocabulary, not the API value set (§11.3.1) | `https://learn.microsoft.com/en-us/fabric/governance/endorsement-overview` | 2026-09-25 |

Reference pages move. Any of these claims is re-checkable by opening the URL and
restating the date; a claim whose date is older than the behaviour it justifies should be
re-read before it is encoded.

### 11.5 What this appendix does **not** authorise

- **No collector change ships with it.** Sprint 6.1 puts the availability record first and
  alone. Wiring a `settingName` into `TENANT_SETTING_MAP`, or carrying
  `endorsementDetails` through Scanner normalisation, is a separate `@collector` boundary
  — and §11.1 says the key that boundary would need is not established.
  *(Still true of Sprint 6.1 itself. The endorsement half of that boundary was
  subsequently taken as its own change — see §11.3.1 and §11.3.2. The
  `TENANT_SETTING_MAP` half remains unwritable for the reason §11.1 gives.)*
- **No rule, no `ObjectType`, no scoring change.** The tenant-setting, endorsement and
  type-reachability rules belong to `@tenant` and `@semantic`, each with its own
  synthetic fixtures, after this record exists.
- **Nothing here clears Sprint 5.1.** Every live confirmation named above stays behind
  5.1's prerequisite: an authorised tenant and an approved read-only service principal.

