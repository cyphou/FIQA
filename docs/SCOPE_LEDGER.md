# Scope Ledger

**What this document is.** A signed disposition for every element of Fabric's shape that
this repository already names in its own code. Today it covers **one** source —
`WORKSPACE_ITEM_KEYS` in [`fabric_iq/collectors/fabric_api.py`](../fabric_iq/collectors/fabric_api.py)
— and its **thirteen** item containers.

Since 2026-09-25 it also carries a second, structurally different table:
[*The review calendar*](#the-review-calendar--classes-that-exist-only-as-prose-3-rows) —
**three** classes of Fabric's shape that exist only as prose (the Microsoft 365 consumption
surfaces, the in-Fabric agent surfaces, the preview Fabric IQ workload). Those rows dispose
no constant, because these classes appear in none; they carry a source, a checked date and
a 90-day review date, and **those dates are enforced** — the gate parses the calendar as a
second section kind and fails the build when a review falls due and no review happened.
What that does and does not buy a reader is stated at the head of the table itself, and how
the enforcement came to exist is recorded in
[*Recorded finding — the experiment that closed this gap*](#recorded-finding--the-experiment-that-closed-this-gap-2026-09-25).
The thirteen ledger rows and the three calendar rows are counted separately and never
aggregated: **13 and 3, never 16** — they are held to different mechanisms, and `watched` is
deliberately not one of the four disposition words.

**Why it exists.** Before this document, the repository's scope read *identically*
whether an omission had been considered and rejected or had never been noticed at all.
That is how the ontology gap survived: the evidence was sitting in a constant the
collector maintains by hand, and nothing said whether its absence from the rule catalogue
was a decision. A verdict's scope should be something an owner signed, not a by-product of
which collector happened to be written first.

**What this document is not.**

- **It is not a detector — but it is partly checked.** A ledger is the baseline a detector
  needs, and since Sprint 7.2 (`e185aab`, with the cross-volume CI fix `f3162ca`) that
  detector exists and reads this file: `scripts/check_scope_ledger.py` runs offline in CI
  and fails the build when this document and `WORKSPACE_ITEM_KEYS` disagree. A fourteenth
  key planted in the constant (`MirroredDatabase`) exits 1, names the key and names
  `@readme` as owing the row — reproduced 2026-09-25, not assumed. Read
  [*What the gate checks, and what it does not*](#what-the-gate-checks-and-what-it-does-not)
  before quoting that as scope-drift detection: it watches **one** declared source and
  six mechanical conditions, and it makes no judgement. **The ledger still makes no gate
  pass.** Closing Sprint 7.1 closes nothing in Sprint 7.2, and no row in this document
  moves a Phase 7 release-gate criterion. Criterion 2 — the reconciliation check runs
  offline in CI as its own named step, appears in the per-change quality gate, and is
  negative-tested three ways — is recorded **met at this revision (2026-09-25)** in
  [`ROADMAP.md`](ROADMAP.md), and it was met by `@tester`'s script and `@orchestrator`'s
  gate-list entry, not by anything written here. The other six criteria are open.
  **Read the roadmap's *Release Gate for Phase 7* for the current status of
  each** — crediting or withholding a criterion is the roadmap owner's act, and this
  bullet goes stale the moment one moves. Criterion 1 in particular requires the untriaged
  set to be empty, and **one row below carries it** (row 13, `GraphModel`, blocked on Q3).
  And the three review-calendar rows are checked for **one thing only**: that a review
  happened by the date the row states. A calendar is not a detector — the absence of a
  review now fails the build, a careless review still passes it, and neither tells anyone
  that the product changed.
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
They are named so nobody reads this document as a complete scope statement. The Sprint 7.2
gate declares the same single source, so an undisposed tenant setting is not a build
failure — it is simply unwatched.

---

## Disposition vocabulary

| Disposition | Means | Must carry |
|---|---|---|
| **assessed** | The engine reaches this item type and judges it | The rule IDs |
| **deliberately excluded** | Considered, and decided against | A reason, an owning agent, a review-by date |
| **open** | Intended, not done | The sprint that would close it |
| **untriaged** | Nobody has answered | The agent who must answer. **This disposition must be empty at the Phase 7 release gate. It is not empty today — one row carries it** (row 13, `GraphModel`, blocked on Q3). |

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
| 10 | `Lakehouse` | **open** | Q1 answered 2026-09-25 by `@dataagent`: a documented agent source is an assessed subject in its own right where a readiness fact lives on it and is unobservable from the agent. `AGT-001` and `AGT-005` judge the agent's *declaration* about a lakehouse (supported type, reachability, routing text authored on the agent); the table and column metadata the generated SQL is written against is a fact about the lakehouse and nothing reads it. In scope as a subject, unassessable today: Sprint 5.1 first (no exercised endpoint returns that metadata), then a `@scorer`-owned object type on the Sprint 6.3 pattern | `@dataagent` (ruling), `@scorer` (object type), `@collector` (read record) | n/a — tracked by the sprint |
| 11 | `KQLDatabase` | **open** | Same ruling as row 10, and Q2 answered with it: the assessed subject is the artefact the agent's source binding names, which the documented list gives as "a KQL database" and not its container (row 12). In scope as a subject, unassessable today for the same two reasons, and closed by the same path — Sprint 5.1, then an object type on the Sprint 6.3 pattern | `@dataagent` (ruling), `@scorer` (object type), `@collector` (read record) | n/a — tracked by the sprint |
| 12 | `Eventhouse` | **deliberately excluded** | Q2's grain half, decided with row 11 and not separately. An eventhouse "is a container that can hold multiple databases" (verified 2026-09-25) and no documented data agent source list names it, so a readiness statement about an eventhouse is a statement about the KQL databases inside it — row 9's duplicate-subject basis applied to a parent instead of a child. Re-opened if a readiness fact is shown to live on the eventhouse alone and to change an agent's answer | `@dataagent` | 2026-12-24 |
| 13 | `GraphModel` | **untriaged** | Q1 is answered and does not settle this row. Graph is a documented data agent source **in preview**, and whether this Scanner key denotes the Fabric graph item is still unverified (Q3, `@collector`). Signing a disposition over a name whose referent is unconfirmed is the exact error the row 9 correction recorded, so the honest state is untriaged and Phase 7 criterion 1 stays open | **`@collector` must answer Q3; `@dataagent` then rules in one line** | — |

**Tally: 3 assessed, 4 open, 5 deliberately excluded, 1 untriaged.** Every key resolves to
exactly one disposition; none carries two.

---

## What the gate checks, and what it does not

Sprint 7.2 made this document executable. Be precise about the size of that claim. The
gate is [`scripts/check_scope_ledger.py`](../scripts/check_scope_ledger.py), owned by
`@tester`, standard library only, and it reads no network. CI runs it as its own named
step, *Check the scope ledger disposes every element in code*. It imports
`WORKSPACE_ITEM_KEYS` rather than keeping a copy, so it cannot drift from the constant it
watches.

Reproduce it — exit 0 at this revision:

```bash
python scripts/check_scope_ledger.py
# Rows parsed:       13 under `WORKSPACE_ITEM_KEYS` (document states 13)
# Calendar rows:     3 watched under 'classes that exist only as prose' (document states 3) -- dates only, no constant
```

**One declared source, two section kinds, six checks:**

| Check | Fires when |
|---|---|
| Parse integrity | The rows parsed disagree with the count this document's own heading states, or the table shape changes so that nothing parses, or the review-calendar section is missing — the vacuous pass is treated as a failure, not as silence |
| Source loadability | `WORKSPACE_ITEM_KEYS` cannot be imported, is renamed or is emptied. A source that disappears must not read as "nothing to check" |
| Undeclared sections | A `## The ledger — …` heading names a constant the gate does not declare in `DECLARED_SOURCES` — rows that parse, print and reconcile against nothing. Added after the hole recorded below, where an invented constant satisfied the parser and exited 0 |
| Undisposed elements | The collector names an item key that has no row here. Verified by planting `MirroredDatabase` in the constant on 2026-09-25: exit 1, naming the key, `@readme` as owing the row and `@collector` as maintaining the constant |
| Stale rows | A row disposes a key `WORKSPACE_ITEM_KEYS` no longer contains — a signed decision about something that is not there |
| Expired or undated reviews | A `deliberately excluded` row carries no `yyyy-mm-dd` review-by date, or **any dated row in either table** has passed its date. The two kinds fail in different words on purpose: an expired exclusion is re-*justified* by its owner, an expired calendar row is re-*read* by its reviewer and the finding written into the review log |

**What it does not cover.** `TENANT_SETTING_MAP`, `ObjectType`, consumption surfaces,
agent kinds, GA/preview status, and every item type this repository does not already name.
Three of those — the Microsoft 365 consumption surfaces, the in-Fabric agent surfaces and
the Fabric IQ workload's preview status — carry a dated **human** review obligation in
[*The review calendar*](#the-review-calendar--classes-that-exist-only-as-prose-3-rows),
and the gate holds those dates but reads nothing about the surfaces themselves: it fails
when nobody reviewed, never when the product moved. The rest are Sprint 7.4's problem and
nothing watches them at all. A clean run means one constant is fully disposed and no
review is overdue. It does not mean this tool's scope is current.

**It does not fire on `untriaged`.** The one remaining untriaged row passes, because
`untriaged` *is* a disposition and naming the agent who owes the answer is a valid landing
state — a missing row is the failure, an honest empty is not. Emptying that set is Phase 7
criterion 1: an owner's judgement, which no script can make.

**The cost, stated before anyone meets it: this gate goes red on 2026-12-25.** Every dated
row in this document carries `2026-12-24`, so they all come due that day and CI fails with
nobody having changed a line. The invariant is **one deliberate per-row edit per dated
row**, each with a re-verified reason or a recorded reading; there is deliberately no bulk
re-dating command. Reproduced by running the audit as of 2026-12-25 and as of 2026-12-24:
**eight expiries and zero** respectively — the five exclusions (rows 6–9 and 12) *and*,
since the calendar was wired up, the three calendar rows (1–3). Four exclusions are owed by
`@readme`, row 12 by `@dataagent`, and all three calendar rows by `@readme`. That is the
review obligation working as designed, not a flake. Add a dated row and the count rises
with it; the number above is what reproduces today, not a ceiling.

**Two scripts parse this file**, so its shape is load-bearing in two places: the gate
asserts the number of rows it reads against the `13 rows` in the ledger heading and the
`3 rows` in the calendar heading, separately and never summed, and
[`tests/test_scope_ledger.py`](../tests/test_scope_ledger.py) imports the same parser.
**The `## The review calendar — …, N rows` heading is itself load-bearing**: the gate
declares `REQUIRED_CALENDAR_SECTIONS = 1`, so deleting or mistyping that heading fails the
build instead of silently un-scheduling all three obligations — reproduced 2026-09-25 by
renaming it, which exits 1 reporting `0 review-calendar section(s) parsed`. The class label
inside the heading may be reworded freely; the count must move with the table. Change a row
deliberately; never reformat the table, renumber it, or edit a heading without moving its
count with it.

---

## The review calendar — classes that exist only as prose, 3 rows

> **Enforcement status, stated first because it changes how the dates below should be
> read: since 2026-09-25 these three rows are gated.** A review-by date that passes
> without a recorded review fails the build, naming the row and its reviewer — verified,
> not assumed, by back-dating row 1 in a copy and watching the gate exit 1. The heading
> above is part of the mechanism: the gate declares `REQUIRED_CALENDAR_SECTIONS = 1`, so
> deleting it fails the build rather than silently un-scheduling all three obligations.
> **What the gate cannot do is unchanged, and is the honest limit of this table:** it
> holds a human to a date, it does not read a vendor page. How this came to be enforced,
> and the hole in the gate found while proving it was not, is recorded in
> [*Recorded finding — the experiment that closed this gap*](#recorded-finding--the-experiment-that-closed-this-gap-2026-09-25).

**Why a calendar, and why it is the honest half.** Of the two gaps found on 2026-09-24, an
offline reconciliation would have caught one and would not have caught the other.
`Ontology` sat in a constant this repository maintains, so it was visible in the code's own
vocabulary and the Sprint 7.2 gate now watches it. The Microsoft 365 consumption surface
appeared in no constant, no endpoint and no item key — **no amount of self-reconciliation
finds a thing the repository has never mentioned.** The only mechanism that would have
caught it is a calendar, and the precedent already works:
[`KNOWN_LIMITATIONS.md` §8](KNOWN_LIMITATIONS.md#8-product-limits-age) — a public source
and an exact verification date per fact.

**State the claim narrowly.** This is a calendar, not a detector. It fails silently when a
human reads carelessly, and that failure cannot be negative-tested. **It guarantees that
somebody looked on a stated date. It never guarantees that they saw.** Wiring the dates to
the gate changed exactly one thing and no more: the *absence* of a review is now a build
failure. A review that happened and missed something is still green, and no test can close
that gap, so none pretends to.

**Cadence: 90 days**, the same cadence the exclusion rows above carry. The reasoning is a
noise argument rather than a preference: three to five reviewable classes on a quarterly
cycle fire a handful of times a year, each fire costing one person one reading pass; a
monthly cadence quadruples the fires without quadrupling the product's rate of shape
change; an annual one leaves a blind spot that outlives most planning horizons. **If a
review repeatedly finds nothing, lengthen the cadence and record why in the log below — do
not delete the row.** A deleted row is indistinguishable from a surface nobody ever
watched, which is the confusion this document exists to remove.

**`watched` is a review obligation, not a scope disposition.** It is deliberately not one
of the four words in the [disposition vocabulary](#disposition-vocabulary) above, and the
rows below are deliberately not ledger rows: they dispose no element of any constant,
because these classes appear in no constant. `watched` means only *"no rule reaches this
and no gate can detect a change in it; a named person re-reads the named sources on the
stated date, and the gate holds them to that date"*. It adds no rule, no `ObjectType`, no
collector read and no scoring change, and **no row here makes any gate pass**.

**The split is enforced in the parser, not only in this prose.** `parse_rows()` returns
ledger rows only and `parse_calendar_rows()` returns these; that separation is deliberate
and `@tester` declined the alternative of teaching the vocabulary test a fifth word,
because a vocabulary containing `watched` would let a real ledger row be dispositioned
`watched` and pass — an element of a constant disposed of by a calendar entry that
reconciles nothing. The two tables are therefore counted separately at every layer: the
gate asserts `13 rows` and `3 rows` against their own headings, the tally below the ledger
counts 13, and **nothing anywhere sums them to 16**.

| # | Class | Obligation | What is watched, the sources re-read, and what the last review found | Reviewer | Review by |
|---|---|---|---|---|---|
| 1 | `m365-consumption-surfaces` | **watched** | **Cowork and Copilot Chat** — the two GA surfaces whose grounding scope decides which assessed object can actually answer, and whose exclusions (`dashboards`, row 4; `dataflows`/`datamarts`, rows 6–7) are quoted from these two pages. Re-read in full **2026-09-25**: [Fabric IQ in Microsoft 365 Copilot Cowork](https://learn.microsoft.com/fabric/iq/connectors/cowork-overview) and [Fabric IQ in Microsoft 365 Copilot Chat](https://learn.microsoft.com/fabric/iq/connectors/microsoft-365-copilot-overview). **Found: no change.** The Cowork plugin is still "a generally available (GA) feature" and "installed by default in Cowork"; it still "grounds on Power BI reports and the semantic models behind them" and still does not ground on "Fabric items that aren't Power BI reports or semantic models, such as lakehouses, eventhouses, ontologies, and data agents"; "Data loss prevention (DLP) isn't currently supported in Cowork". Copilot Chat data answering from Power BI content is still GA, DLP policies there "also apply", and its exclusion of agents and ontologies is still the conditional one — they "can't answer questions in Copilot Chat **without an explicitly published Microsoft 365 agent**" | `@readme` (accuracy and dating); a change in grounding scope routes to `@scorer` (Sprint 6.2) and to `@semantic` | 2026-12-24 |
| 2 | `in-fabric-agent-surfaces` | **watched** | **What counts as an agent inside Fabric, its GA/preview status, and its documented data sources** — the set that decides whether the 15 `AGT-*` rules still address the right subject, and the list rows 10–13 rest on. Re-read in full **2026-09-25**: [Fabric data agent concepts](https://learn.microsoft.com/fabric/data-science/concept-data-agent), [What is graph in Microsoft Fabric?](https://learn.microsoft.com/fabric/graph/overview) and [What is Copilot in Fabric?](https://learn.microsoft.com/fabric/fundamentals/copilot-fabric-overview). **Found: no change to the source list.** "Data agent in Microsoft Fabric is a generally available feature"; the documented sources remain "a warehouse, a lakehouse, a Power BI semantic model, a KQL database, a mirrored database, or an ontology", with graph still preview. Recorded as context rather than as a disposition change: the page states that Purview risk discovery and auditing for agents is "currently in preview", and Copilot in Fabric continues to carry per-workload preview features | `@readme` (accuracy and dating); a change to the documented source list routes to `@dataagent`, who owns the Q1 ruling it would disturb | 2026-12-24 |
| 3 | `fabric-iq-workload-preview` | **watched** | **The GA/preview status of the Fabric IQ workload and of its ontology item** — the pin under Sprint 6.3, under row 5's `open` disposition, and under any claim this tool makes about ontology readiness. A move to GA is a roadmap event, not a documentation edit. Re-read in full **2026-09-25**: [What is Fabric IQ?](https://learn.microsoft.com/fabric/iq/overview) and [What is ontology (preview)?](https://learn.microsoft.com/fabric/iq/ontology/overview). **Found: still preview.** The ontology article is titled "What is ontology (preview)?" and states the item is "part of the Fabric IQ (preview) workload"; the workload overview names "ontology (preview) and semantic model" as the two core items | `@readme` (accuracy and dating); a GA transition routes to `@roadmap-planner` (which sprint) and `@collector` (read record) | 2026-12-24 |

**Three rows, one class each, and the set is deliberately small.** These are the three
classes Sprint 7.3 names for its smallest slice. Tenant settings, capacity SKU thresholds
and item types this repository has never heard of are **not** on this calendar and nothing
watches them — the second of those is Sprint 7.4's problem, and saying so is cheaper than
letting a reader assume coverage.

### The review log — a review that found nothing is still evidence

A nil result is the normal outcome of a quarterly read and it **must be written down with
its date and the sources consulted**, otherwise the next reviewer cannot distinguish a
checked surface from an unchecked one. Append a row per review; never overwrite one.

| Review date | Class | Reviewer | Sources consulted | Finding | Next review |
|---|---|---|---|---|---|
| 2026-09-25 | `m365-consumption-surfaces` | `@readme` | `cowork-overview`, `microsoft-365-copilot-overview` (both read live, in full) | **Nil — no change.** GA status, grounding scope, the DLP asymmetry (applies in Copilot Chat, "isn't currently supported in Cowork") and the conditional agent/ontology exclusion all read exactly as recorded on 2026-09-24/25. The Copilot Chat page reports "Last updated on 2026-09-23", so the re-read covered a page revised two days before it | 2026-12-24 |
| 2026-09-25 | `in-fabric-agent-surfaces` | `@readme` | `concept-data-agent`, `graph/overview`, `copilot-fabric-overview` (all read live, in full) | **Nil — no change to anything a row depends on.** The six-source list and graph's preview status are unchanged. Two facts newly written down here because nothing in this document had recorded them: the data agent itself is stated GA, and agent-related Purview risk discovery and auditing is stated preview. Neither moves a disposition | 2026-12-24 |
| 2026-09-25 | `fabric-iq-workload-preview` | `@readme` | `iq/overview`, `iq/ontology/overview` (both read live, in full) | **Nil — still preview.** Both the ontology item and the Fabric IQ workload are labelled preview on the live pages. Row 5 and Sprint 6.3 stand as written | 2026-12-24 |

**No review in this log found a change**, and that is the expected shape of a first entry
written on the same day the rows were sourced. It is recorded anyway, because the value of
the log is only realised when a later reviewer can tell *checked and unchanged* from *never
checked*.

### Recorded finding — the experiment that closed this gap (2026-09-25)

**Kept, though its premise is gone, and rewritten in the past tense.** Nothing below
describes a gap that exists today: these rows are gated. It is kept because it records a
real experiment that found a real hole *in the anti-drift gate itself*, and because it is
the reason three things in the current design look the way they do — the calendar's own
heading kind, the undeclared-sections check, and `REQUIRED_CALENDAR_SECTIONS`. Deleting it
would leave those three looking like taste.

**The state when the calendar was first written.** The Sprint 7.2 gate was expected to
cover these rows "with no new mechanism". That was half true, and the false half was the
half that mattered:

- `check_reviews()` in [`scripts/check_scope_ledger.py`](../scripts/check_scope_ledger.py)
  iterated **every parsed row** and validated any `yyyy-mm-dd` it found. A dated row the
  parser saw did get expiry-checked.
- But `parse_sections()` only collected rows under a heading matching
  `` ## The ledger — `CONSTANT`, N rows ``. **These three classes have no constant — that
  is the entire point of them**, so the parser never saw them and their dates never fired.

**Two options, and no honest third.** Writing the rows under a `## The ledger — …` heading
would have required an identifier where no importable constant exists: a fake constant,
the documentation equivalent of a reasonless exclusion, which would also have made the
gate print a source it never reconciled. Writing them under an ordinary `## ` heading meant
the parser never saw them and the expiry check never fired. **The choice made was the
second, declared rather than concealed** — a review obligation that silently never comes
due is worse than none, because it looks scheduled — and the gap was stated in the banner
above the dates rather than left to be discovered.

**Verified, not assumed, in both directions.** Three copies of this file were audited with
`python scripts/check_scope_ledger.py --ledger <copy>`. Row 1 back-dated to `2025-01-01`:
**exit 0, clean** — the gap, reproduced. Ledger row 6 (`dataflows`) back-dated the same
way: exit 1 naming the row and its owner — the expiry mechanism worked and simply did not
reach this table. A third copy whose calendar heading was reshaped into the parser's
section form: exit 1 on the back-dated calendar row, which located the entire gap in the
heading regex and nowhere else. **The first of those three now exits 1** — re-run against
the wired gate on 2026-09-25, reporting `review calendar row 1 (m365-consumption-surfaces,
watched) was due for review on 2025-01-01` and naming `@readme`.

**The hole the experiment found, routed rather than exploited.** In that third copy the
parser accepted a section naming `REVIEW_CALENDAR`, a constant that does not exist,
**without complaint**: nothing checked that a parsed section corresponded to a *declared*
source, so an invented constant satisfied the parser, was printed as a parsed source, and
exited 0 — a vacuous gate living inside the anti-drift gate. The shortcut was available,
was the cheapest way to make these dates fire, and was not taken; it was routed to
`@tester` instead. That is now **check 3 in the table above**, and the same assertion
catches the quieter case it implies: a *real* constant added to this document and never
declared, whose rows parse, print and reconcile against nothing.

**What `@tester` then changed** (not done here — this agent does not own `scripts/`):

1. `parse_sections()` learned a **second section kind**, `## The review calendar — …, N
   rows`, parsed with the same `ROW` regex and held to the same stated-count assertion.
2. Those rows are kept **out of** the `by_source` reconciliation, because they dispose no
   constant and the undisposed and stale checks would fail on arrival over classes that
   are in no constant by definition.
3. The vocabulary stayed at four words. `parse_rows()` returns ledger rows only and
   `parse_calendar_rows()` is separate — the proposal to teach the vocabulary test a fifth
   word was **declined**, because it would have let a real ledger row be dispositioned
   `watched` and pass. The tally still reads **13**.
4. The direction that matters is negative-tested: a back-dated calendar row exits 1 naming
   the row and its reviewer, and the failure text tells the reviewer to *re-read sources*
   rather than to re-justify a reason, because that is the work an expired calendar row
   actually asks for.
5. `REQUIRED_CALENDAR_SECTIONS = 1` was declared, so deleting or mistyping the calendar
   heading fails the build instead of silently un-scheduling all three obligations —
   reproduced here by renaming the heading, which exits 1 with
   `0 review-calendar section(s) parsed`.

Writing the rows in the ledger's exact six-column shape was what made this cheap: when the
heading was recognised, **nothing in the table above had to be edited to become
enforceable**, and no date moved.

**What did not change.** The calendar is still a calendar. The forward cost it adds is in
[*What the gate checks*](#what-the-gate-checks-and-what-it-does-not) above — eight dated
rows now come due on 2026-12-24, not five.

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
exclusion deliberately did **not** pre-empt row 10, and that conditional has since fired in
the direction it anticipated: on 2026-09-25 `@dataagent` ruled lakehouses in scope as
subjects (row 10, now `open`), and the subject is still the lakehouse — this row did not
move. It is re-opened only if a readiness fact turns out to live on the endpoint and
nowhere else.

### 10–13 — the asymmetry, and the rule that resolves it

The repository assesses the **agent** (15 rules) and **none of its documented sources**.
The documented source list is "a warehouse, a lakehouse, a Power BI semantic model, a KQL
database, a mirrored database, or an ontology" (verified 2026-09-25), plus graph in preview
and Microsoft Graph. Of those, the semantic model *is* assessed — because it is also a
Power BI object with its own rules, not because anyone decided agent sources were in scope.

**Q1, answered 2026-09-25 by `@dataagent`.** A data agent's data sources *are* assessed
subjects in their own right — but only on a stated test, because "the agent reads it" would
swallow the whole estate. The test is: **the assessed subject is the artefact the agent's
source binding names, and it is a subject where a readiness fact lives on that artefact and
cannot be observed from the agent.** Three existing rules already read sources and none of
them contradicts this, because two of them read the *agent*:

- `AGT-001` judges supported type and reachability — attributes of the agent's binding.
- `AGT-005` judges the routing description, which is **authored on the agent**, not on the
  lakehouse. Both are agent attributes wearing a source's name.
- `AGT-003` is the exception, and it is the precedent. It defers to the source's **own
  scorecard** because the readiness fact — the metadata and Prep-for-AI configuration "the
  agent's DAX generator reads", in the rule's own remediation text — lives on the model and
  is invisible from the agent. A lakehouse and a KQL database carry the exact analogue: the
  table and column names and descriptions the generated SQL or KQL is written against.

So rows 10 and 11 are **in scope as subjects**, and the only reason they are not assessed is
that the subject does not exist yet. That is `open`, not `assessed` and not `excluded`:

- Not `assessed` — there is no `ObjectType`, no rule, and no read. `API_REALITY_MATRIX.md`
  records that not one tenant-admin endpoint has returned `200` here, and that even a
  semantic model's `tables` and `columns` are `absent` on both exercised surfaces. A rule
  family born today would be `NOT_EVALUATED` on every run, which is a scorecard-shaped hole
  — the same trap Sprint 6.3 names for the ontology object type.
- Not `excluded` — an exclusion here would sign the claim that a lakehouse's own metadata
  cannot affect an agent's answer, which contradicts `AGT-003`'s remediation text and the
  product behaviour it describes. That is the reasonless exclusion this document exists to
  prevent, arriving with a reason that happens to be false.

**Q2, answered with row 11: the grain is the KQL database, not the eventhouse.** The
documented source is "a KQL database"; an eventhouse "is a container that can hold multiple
databases" (verified 2026-09-25) and appears in no documented source list. Two databases in
one eventhouse can differ in exactly the metadata quality that decides an answer, so a
container-level readiness statement is either a restatement of its children or a statement
about capacity and caching that belongs to the workspace and capacity rules. Row 12 is
therefore **excluded as a duplicate subject** — row 9's basis applied to a *parent* rather
than a *child*, and both fall out of the same test: the subject is the artefact the binding
names. Its re-open condition is written into the row and is real, not decorative: a
readiness fact that lives on the eventhouse alone and changes an agent's answer.

**Row 13 stays `untriaged`, deliberately.** Q1 does not settle it, because the obstacle is
not the judgement — it is that nobody has confirmed the key denotes the Fabric graph item at
all, and graph is preview. Applying the Q1 test to `GraphModel` today would sign a
disposition over a name whose referent is unverified, which is precisely the mistake the
correction below records. Q3 is routed to `@collector` and is now the **only** thing holding
this row. **Phase 7 release-gate criterion 1 therefore stays open**, which is the correct
outcome of this triage rather than a failure of it; crediting or withholding that criterion
is the roadmap owner's act in any case.

**What this ruling does not do.** It adds no rule, no `ObjectType`, no collector read and no
scoring change, and it moves no score. `AGT-003` behaves exactly as before — and its pattern
remains answerable for **one source type out of six**, which is now a recorded consequence
rather than an unexamined one: `fabric_iq/scoring.py` builds `source_scores` only for
sources whose `type` is `semantic_model`, so "every source is itself ready" is literally
unasked for a lakehouse. Whether that pattern generalises once a source object type exists,
or whether the agent should instead carry a per-source-type readiness rule, is a rule-design
question (Q5 below), and which sprint carries the object type and its collection
prerequisite is the roadmap owner's (Q6). Both are routed, neither is settled here.

**A correction, recorded because it was nearly written as fact.** A working assumption
held that `SQLAnalyticsEndpoint` was itself a documented data agent data source. It is
not: neither *Fabric data agent creation* nor *Create a Fabric data agent* names a SQL
analytics endpoint anywhere on the page (both read 2026-09-25). The row above rests on
the auto-provisioning fact instead.

---

## Questions routed, and the two now answered

| # | Question | Routed to | Rows it settles | Status |
|---|---|---|---|---|
| Q1 | Are Fabric data agent **data sources** assessed subjects in their own right, or is the agent the only assessed subject and its sources merely inputs? | `@dataagent` | 10, 11, 12 (**not** 13) | **Answered 2026-09-25 by `@dataagent`.** They are subjects — on a stated test: the assessed subject is the artefact the agent's source binding names, where a readiness fact lives on that artefact and cannot be observed from the agent. Rows 10 and 11 become `open`, row 12 `deliberately excluded`. It does not settle row 13, which turns on Q3 |
| Q2 | If sources are in scope, at what **grain** — the eventhouse, or the KQL database inside it? | `@dataagent` | 11, 12 | **Answered 2026-09-25 with Q1, not separately.** The KQL database: it is what the documented source list names and what the binding attaches to. The eventhouse is the container, excluded as a duplicate subject on row 9's basis |
| Q3 | Does the Scanner key `GraphModel` correspond to the Fabric **graph** item, and is any of its metadata readable by a read-only caller? | `@collector` | 13 | **Open**, and now the only thing holding row 13 — the judgement it needed is made, the identification is not |
| Q4 | Should an upstream producer's refresh state become an input to a **semantic-model** rule, given that `SEM-016` currently reads freshness from the model alone? | `@semantic` | 6, 7 (does not change their disposition; may add a rule elsewhere) | **Open** |
| Q5 | Once a source object type exists, does `AGT-003`'s defer-to-the-source's-own-scorecard pattern generalise to a lakehouse and a KQL database, or should the agent carry a per-source-type readiness rule instead? | `@dataagent` (rule design), with `@scorer` on the object type | none — raised by the Q1 ruling, changes no disposition | **Open.** Today `fabric_iq/scoring.py` populates `source_scores` only for `semantic_model` sources, so `AGT-003` is answerable for one source type of six |
| Q6 | Which sprint owns the source-as-subject object type and its collection prerequisite? No sprint currently carries rows 10 and 11; the closing path named there (Sprint 5.1, then the Sprint 6.3 pattern) is a prerequisite and a precedent, not an owner. | `@orchestrator` (roadmap owner) | 10, 11 — their **closing sprint**, not their disposition | **Open.** No roadmap change is made here; naming a sprint that does not exist would be the scheduling equivalent of a reasonless exclusion |

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
| The Fabric IQ plugin in Cowork "is a generally available (GA) feature of Microsoft Fabric" and "is installed by default in Cowork" | [Fabric IQ in Microsoft 365 Copilot Cowork](https://learn.microsoft.com/fabric/iq/connectors/cowork-overview) | 2026-09-25, live page |
| "Data loss prevention (DLP) isn't currently supported in Cowork" — while in Copilot Chat "Data loss prevention (DLP) policies also apply" | [Cowork](https://learn.microsoft.com/fabric/iq/connectors/cowork-overview) and [Copilot Chat](https://learn.microsoft.com/fabric/iq/connectors/microsoft-365-copilot-overview) | 2026-09-25, live pages |
| "Fabric data agents and ontologies can't answer questions in Copilot Chat without an explicitly published Microsoft 365 agent" — the exclusion is conditional, not absolute | [Fabric IQ in Microsoft 365 Copilot Chat](https://learn.microsoft.com/fabric/iq/connectors/microsoft-365-copilot-overview) | 2026-09-25, live page |
| "Data agent in Microsoft Fabric is a generally available feature"; agent-related Purview risk discovery and auditing is "currently in preview" | [Fabric data agent concepts](https://learn.microsoft.com/fabric/data-science/concept-data-agent) | 2026-09-25, live page |
| The ontology item is "part of the Fabric IQ (preview) workload"; the workload overview names "ontology (preview) and semantic model" as its two core items | [What is ontology (preview)?](https://learn.microsoft.com/fabric/iq/ontology/overview) and [What is Fabric IQ?](https://learn.microsoft.com/fabric/iq/overview) | 2026-09-25, live pages |

The last five rows are the sourcing behind
[*The review calendar*](#the-review-calendar--classes-that-exist-only-as-prose-3-rows) and
are repeated inside those rows deliberately: a reviewer reading a calendar row must see the
source without navigating away from the date it is held to.

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

- **Review cadence: 90 days**, the cadence Sprint 7.3 proposes, applied in two places.
  All **five** `deliberately excluded` ledger rows carry **2026-12-24** — rows 6–9 owed by
  `@readme` and row 12 owed by `@dataagent`, who excluded it. The **three**
  review-calendar rows carry the same date and the same cadence, and are owed by `@readme`.
  Both are enforced by the same expiry check: re-verified with the audit on 2026-09-25,
  **eight expiries as of 2026-12-25 — five exclusions and three calendar rows — and none
  as of 2026-12-24.** A calendar date passing unnoticed is now a build failure; what it is
  still not is a signal that the product moved.
- **There is no bulk re-dating command, and there must not be one.** Clearing a review
  costs one deliberate per-row edit with a recorded reason. That cost is the point: a
  guard people regenerate without reading is decoration. The absence is now asserted by
  test — no `--update`, `--accept-all`, `--fix`, `--regenerate` or `--ignore` flag exists,
  and `--update` exits 2.
- **A review that found nothing is still evidence** and is written down with its date and
  the sources consulted, otherwise the next reviewer cannot tell a checked row from an
  unchecked one. For the calendar rows there is a place to write it: append to
  [*The review log*](#the-review-log--a-review-that-found-nothing-is-still-evidence) and
  never overwrite an entry. Its first three entries are all nil results, recorded as such.
- **Changing a disposition is an owner's act.** `@readme` owns this document's accuracy and
  its dated sourcing; it does not own the judgements in rows 10–13 and did not write them.
  Those rows were ruled by `@dataagent` on 2026-09-25 (Q1 and Q2), row 13 excepted — it
  waits on `@collector`'s Q3 — and row 12's review-by date is `@dataagent`'s to clear.

**Ownership.** This document is a collection-capability claim and is therefore a
`REQUIRED_DOCS` entry in `scripts/check_agent_ownership.py`, accountable to `@readme`.
Since Sprint 7.2 it is also the input to `scripts/check_scope_ledger.py`, which `@tester`
owns: the accuracy of the rows is `@readme`'s, the checking of them is not.

| Last full review | Reviewer | Source covered |
|---|---|---|
| 2026-09-25 | `@readme` | `WORKSPACE_ITEM_KEYS` — rows 1–9 (9 of 13), plus this document's structure, sources and review dates |
| 2026-09-25 | `@dataagent` | `WORKSPACE_ITEM_KEYS` — rows 10–13 (4 of 13): the Q1/Q2 ruling, row 12's exclusion reason and date, and row 13 left `untriaged` pending Q3 |
| 2026-09-25 | `@readme` | **The review calendar** — all 3 rows, sourced and dated from a live re-read of the six Learn pages named in their cells. Findings: three nil results, logged individually |

**13 of 13 ledger rows reviewed on 2026-09-25, by two reviewers, and 3 of 3 calendar rows
by one.** The split is recorded rather than aggregated: rows 10–13 are `@dataagent`'s
judgement, and a review record that attributed them to `@readme` would be the same class of
defect as a stale count. The two tables are also counted separately — **13 and 3, never
16** — because they are held to different mechanisms: the thirteen are reconciled against a
constant, the three are reconciled against nothing and are held only to their dates.
