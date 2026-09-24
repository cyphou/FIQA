"""Blinded practitioner calibration: the mechanism, not the verdict.

``docs/KNOWN_LIMITATIONS.md`` §5 states that the dimension weights and the
85/70/50 thresholds are *reasoned*, not calibrated. ``docs/ROADMAP.md`` Sprint 5.3
requires the evidence that could one day justify changing them: a blinded
worksheet, two or more practitioners labelling a bounded sample independently,
and a record of the agreement **and every disagreement**.

This module builds that mechanism. It deliberately stops short of the conclusion.

What it does
------------

1. :func:`build_worksheet` draws a reproducible, stratified, bounded sample from an
   :class:`~fabric_iq.models.AssessmentRun` and renders the *facts* a practitioner
   needs in order to judge readiness — with every trace of the tool's own verdict
   removed (:data:`BLINDED_FIELDS`).
2. :func:`write_worksheet` emits a CSV a practitioner can fill in Excel, an
   instruction sheet, and a **separate, non-blinded key file** that only the
   coordinator holds.
3. :func:`analyse` takes the filled worksheets back and reports inter-rater
   agreement first, tool agreement second, and enumerates every disagreement.

What it must never do
---------------------

**It proposes no number.** No optimiser, no fitted weight, no "recommended
threshold". The roadmap is explicit: "No change is required merely to increase
agreement." A calibration routine that also proposes the correction it measures
has stopped being evidence and started being a thumb on the scale. Any weight or
threshold change remains a human decision, reviewed by ``@scorer``, with its own
regression test in ``tests/test_scoring.py``. :class:`CalibrationReport` therefore
carries an explicit, tested ``proposals: []``.

Privacy
-------

A calibration sample drawn from a real tenant is customer data: object names,
workspace names, measured metadata. Every file this module writes is treated as an
evidence sink exactly like ``artifacts``/``lakehouse``/``powerbi_report`` —
git-ignored destination, never committed. :data:`CALIBRATION_SINK_ROOT` names the
default destination and :func:`calibration_sinks` enumerates the destinations for
``scripts/check_evidence_sinks.py``, so a new output file cannot skip the gate.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from fabric_iq import RULESET_VERSION
from fabric_iq.errors import ConfigurationError, ScoringError
from fabric_iq.models import (
    AssessmentRun,
    ObjectType,
    ReadinessStatus,
    RuleStatus,
    Scorecard,
    utcnow,
)

# ── the evidence sink ────────────────────────────────────────────────────────

#: Default destination for every calibration file. ``artifacts/`` is already a
#: committed ignore rule and already a member of ``SINK_ROOTS`` in
#: ``scripts/check_evidence_sinks.py``, so the privacy guarantee holds on the day
#: this lands rather than on the day another agent wires a new root.
CALIBRATION_SINK_ROOT = "artifacts/calibration"

#: Filename suffixes the writers emit, with the reason each must stay untracked.
CALIBRATION_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("_calibration_worksheet.csv", "blinded worksheet: measured facts about tenant objects"),
    ("_calibration_key.json", "un-blinded key: object names, ids and the tool's verdicts"),
    ("_calibration_instructions.md", "labelling protocol, carries the run id"),
    ("_calibration_agreement.json", "agreement report: pseudonyms, labels, rationales"),
    ("_calibration_disagreements.csv", "every disagreement, object by object"),
)


def calibration_sinks(run_id: str = "20260101T000000Z") -> list[tuple[str, str]]:
    """Every destination this module can write, as ``(path, why)`` pairs.

    Shaped for ``scripts/check_evidence_sinks.py::writer_sinks``, which already
    imports ``GOLD_TABLES`` from the package for the same reason: a destination
    enumerated by the writer cannot drift away from the gate that protects it.
    Both the default root and a relocated one are covered, because the basenames
    have to be ignored wherever ``--calibration`` is pointed.
    """
    sinks: list[tuple[str, str]] = [(CALIBRATION_SINK_ROOT + "/", "--calibration default folder")]
    for suffix, why in CALIBRATION_ARTIFACTS:
        sinks.append((f"{CALIBRATION_SINK_ROOT}/{run_id}{suffix}", why))
        sinks.append((f"elsewhere/{run_id}{suffix}", f"{why} (relocated --calibration)"))
    return sinks


# ── sampling parameters ──────────────────────────────────────────────────────

#: Roadmap Sprint 5.3: "a bounded 20-30 object sample".
ROADMAP_SAMPLE_BOUNDS = (20, 30)
DEFAULT_SAMPLE_SIZE = 24

#: Any fixed value works; what matters is that the value is recorded in the key
#: file and the instruction sheet, so the draw can be reproduced and audited.
DEFAULT_SEED = 5303

#: Pseudonym prefix per object type. Deliberately distinct from rule-id prefixes
#: (``SEM-007``, ``REP-004``) so a worksheet label can never be read as a rule.
TYPE_CODE: dict[ObjectType, str] = {
    ObjectType.TENANT: "TN",
    ObjectType.CAPACITY: "CP",
    ObjectType.WORKSPACE: "WS",
    ObjectType.SEMANTIC_MODEL: "SM",
    ObjectType.REPORT: "RP",
    ObjectType.DATA_AGENT: "DA",
}


# ── the blinding contract ────────────────────────────────────────────────────

#: Fields that must never reach a worksheet row. Asserted in full at write time
#: by :func:`assert_blinded`, not spot-checked.
BLINDED_FIELDS = frozenset(
    {
        "score",
        "raw_score",
        "status",
        "eligible",
        "confidence",
        "coverage",
        "dimension_scores",
        "blocking_findings",
        "findings",
        "notes",
        "severity",
        "rule_id",
        "rule_status",
        "object_id",
        "object_name",
        "parent_id",
        "outcome",
        "readiness_status",
        "band",
        "effort",
        "priority",
    }
)

#: Verdict vocabulary that must not appear in any worksheet cell. This is a
#: value-level smoke check layered on top of the structural guarantee above: the
#: structure cannot carry a verdict field, and the text cannot carry the words the
#: engine uses to publish one. ``ready`` is matched as a standalone word so that
#: "readiness" and "already" do not trip it.
#:
#: ``passed``, ``failed`` and ``partial`` are deliberately **not** on this list.
#: They are ordinary domain English — "118/120 refreshes succeeded ... failed=2",
#: "12/12 critical answers correct" — and banning them would fail the build on a
#: measured fact rather than on a leak, which trains people to weaken the gate. The
#: per-rule status is excluded structurally instead: no worksheet column carries a
#: rule outcome at all, so there is nothing for those words to leak.
FORBIDDEN_VALUE_TOKENS: tuple[str, ...] = tuple(
    sorted(
        {status.value for status in ReadinessStatus}
        | {RuleStatus.NOT_EVALUATED.value, RuleStatus.NOT_APPLICABLE.value}
    )
)

_TOKEN_PATTERNS = tuple(
    (token, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", re.IGNORECASE))
    for token in FORBIDDEN_VALUE_TOKENS
)


class CalibrationLabel(str, Enum):
    """The vocabulary a practitioner may use.

    The first four are rungs on one ladder. ``INSUFFICIENT_EVIDENCE`` is not: it
    means "the facts I was given do not let me judge this object", which is a
    statement about the evidence, not about the object. Forcing a labeler onto the
    ladder when they cannot see enough manufactures a label, which is the labeling
    equivalent of scoring an absence as a failure.
    """

    READY = "ready"
    READY_WITH_CONDITIONS = "ready_with_conditions"
    REMEDIATION_REQUIRED = "remediation_required"
    NOT_READY = "not_ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


#: Position on the readiness ladder. ``INSUFFICIENT_EVIDENCE`` is absent by design.
ORDINAL_RANK: dict[CalibrationLabel, int] = {
    CalibrationLabel.NOT_READY: 0,
    CalibrationLabel.REMEDIATION_REQUIRED: 1,
    CalibrationLabel.READY_WITH_CONDITIONS: 2,
    CalibrationLabel.READY: 3,
}

#: Spellings accepted when a filled worksheet comes back. Practitioners type prose.
LABEL_ALIASES: dict[str, CalibrationLabel] = {
    "ready": CalibrationLabel.READY,
    "r": CalibrationLabel.READY,
    "ready_with_conditions": CalibrationLabel.READY_WITH_CONDITIONS,
    "ready with conditions": CalibrationLabel.READY_WITH_CONDITIONS,
    "conditional": CalibrationLabel.READY_WITH_CONDITIONS,
    "rwc": CalibrationLabel.READY_WITH_CONDITIONS,
    "remediation_required": CalibrationLabel.REMEDIATION_REQUIRED,
    "remediation required": CalibrationLabel.REMEDIATION_REQUIRED,
    "remediation": CalibrationLabel.REMEDIATION_REQUIRED,
    "rr": CalibrationLabel.REMEDIATION_REQUIRED,
    "not_ready": CalibrationLabel.NOT_READY,
    "not ready": CalibrationLabel.NOT_READY,
    "nr": CalibrationLabel.NOT_READY,
    "insufficient_evidence": CalibrationLabel.INSUFFICIENT_EVIDENCE,
    "insufficient evidence": CalibrationLabel.INSUFFICIENT_EVIDENCE,
    "cannot_judge": CalibrationLabel.INSUFFICIENT_EVIDENCE,
    "cannot judge": CalibrationLabel.INSUFFICIENT_EVIDENCE,
    "not_evaluated": CalibrationLabel.INSUFFICIENT_EVIDENCE,
    "ie": CalibrationLabel.INSUFFICIENT_EVIDENCE,
}

#: The tool's own published status, expressed in the labelers' vocabulary so the
#: two can be compared at all. ``NOT_EVALUATED`` maps to ``INSUFFICIENT_EVIDENCE``
#: and therefore stays off the ordinal ladder on both sides of the comparison.
TOOL_STATUS_AS_LABEL: dict[ReadinessStatus, CalibrationLabel] = {
    ReadinessStatus.READY: CalibrationLabel.READY,
    ReadinessStatus.READY_WITH_CONDITIONS: CalibrationLabel.READY_WITH_CONDITIONS,
    ReadinessStatus.REMEDIATION_REQUIRED: CalibrationLabel.REMEDIATION_REQUIRED,
    ReadinessStatus.NOT_READY: CalibrationLabel.NOT_READY,
    ReadinessStatus.NOT_EVALUATED: CalibrationLabel.INSUFFICIENT_EVIDENCE,
}

#: Identifier used for the engine when it appears as one voice among the raters.
TOOL_RATER_ID = "tool"

WORKSHEET_COLUMNS = (
    "label",
    "object_type",
    "parent_label",
    "observed_facts",
    "evidence_references",
    "readiness_label",
    "rationale",
)


def parse_label(raw: str) -> CalibrationLabel | None:
    """Map a practitioner's spelling to a label, or ``None`` when the cell is blank.

    Raises :class:`ConfigurationError` on a non-blank value that is not in the
    vocabulary. A misspelt label is not silently dropped: a dropped label is a
    missing data point nobody investigates, and the sample is only 20-30 rows.
    """
    text = (raw or "").strip().lower().replace("-", "_")
    if not text:
        return None
    if text in LABEL_ALIASES:
        return LABEL_ALIASES[text]
    collapsed = re.sub(r"\s+", " ", text.replace("_", " "))
    if collapsed in LABEL_ALIASES:
        return LABEL_ALIASES[collapsed]
    raise ConfigurationError(f"unknown readiness label: {raw!r}")


# ── worksheet construction ───────────────────────────────────────────────────


@dataclass(frozen=True)
class WorksheetRow:
    """One blinded row handed to a practitioner.

    Every field here is either a fact about the object or a blank the labeler
    fills. Nothing on this row is derived from the tool's verdict.
    """

    label: str
    object_type: str
    parent_label: str
    observed_facts: str
    evidence_references: str
    readiness_label: str = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return {column: getattr(self, column) for column in WORKSHEET_COLUMNS}


@dataclass(frozen=True)
class KeyEntry:
    """The un-blinded counterpart of one worksheet row. Never handed to a labeler."""

    label: str
    object_id: str
    object_name: str
    object_type: str
    parent_label: str
    band: str
    tool_status: str
    tool_label: str
    score: float
    raw_score: float
    eligible: bool
    confidence: float
    coverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "object_type": self.object_type,
            "parent_label": self.parent_label,
            "band": self.band,
            "tool_status": self.tool_status,
            "tool_label": self.tool_label,
            "score": round(self.score, 2),
            "raw_score": round(self.raw_score, 2),
            "eligible": self.eligible,
            "confidence": round(self.confidence, 4),
            "coverage": round(self.coverage, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyEntry":
        return cls(
            label=str(data.get("label", "")),
            object_id=str(data.get("object_id", "")),
            object_name=str(data.get("object_name", "")),
            object_type=str(data.get("object_type", "")),
            parent_label=str(data.get("parent_label", "")),
            band=str(data.get("band", "")),
            tool_status=str(data.get("tool_status", "")),
            tool_label=str(data.get("tool_label", "")),
            score=float(data.get("score", 0.0) or 0.0),
            raw_score=float(data.get("raw_score", 0.0) or 0.0),
            eligible=bool(data.get("eligible", False)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            coverage=float(data.get("coverage", 0.0) or 0.0),
        )


@dataclass(frozen=True)
class Worksheet:
    """A blinded sample plus the key that unblinds it.

    The two halves travel separately on purpose. ``rows`` is what a practitioner
    receives; ``key`` stays with the coordinator. Nothing in ``rows`` can be joined
    back to ``key`` except through the pseudonym.
    """

    run_id: str
    ruleset_version: str
    seed: int
    requested_size: int
    rows: list[WorksheetRow]
    key: list[KeyEntry]
    strata: dict[str, int]
    pseudonyms: dict[str, dict[str, str]]
    generated_at: str = field(default_factory=utcnow)
    notes: list[str] = field(default_factory=list)

    def key_to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ruleset_version": self.ruleset_version,
            "generated_at": self.generated_at,
            "sampling": {
                "seed": self.seed,
                "requested_size": self.requested_size,
                "actual_size": len(self.rows),
                "roadmap_bounds": list(ROADMAP_SAMPLE_BOUNDS),
                "strata": self.strata,
            },
            "notes": self.notes,
            "privacy": (
                "Un-blinded calibration key: object and workspace names plus the tool's "
                "verdicts. Tenant-derived evidence. Never hand this file to a labeler and "
                "never commit it."
            ),
            "entries": [entry.to_dict() for entry in self.key],
            "pseudonyms": self.pseudonyms,
        }


def _band(card: Scorecard) -> str:
    """Quality band used to stratify *selection*.

    Stratifying by band is how the sample avoids being all-green or all-broken.
    The band is computed from the tool's verdict and is recorded only in the key
    file; it never appears in a worksheet row.
    """
    if card.status is ReadinessStatus.NOT_EVALUATED:
        return "not_evaluated"
    if card.score >= 85.0:
        return "top"
    if card.score >= 70.0:
        return "high"
    if card.score >= 50.0:
        return "mid"
    return "low"


def _trim(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


#: A reference to the engine's own 0-100 output. ``scorecard``/``scorecards`` are
#: excluded by the word boundary, so an evidence *reference* survives while the
#: value behind it does not.
_VERDICT_QUOTE = re.compile(r"(?<![A-Za-z])scores?(?![A-Za-z])|\d+\s*/\s*100", re.IGNORECASE)


def _quotes_a_verdict(detail: str, observed: dict[str, Any]) -> bool:
    """True when a rule outcome repeats the engine's verdict on some object."""
    if any("score" in str(key).lower() for key in observed):
        return True
    return bool(_VERDICT_QUOTE.search(detail or ""))


def _pseudonymise(text: str, name_map: Sequence[tuple[str, str]]) -> str:
    """Replace every known object name in ``text`` with its pseudonym.

    Measured facts quote tenant-authored identifiers: a table called
    ``FIN_PNL_CONSO`` inside a model of the same name, a capacity called
    ``Contoso-Dev`` inside the ``Contoso`` tenant. Pseudonymising the row label and
    leaving the same name in the fact text would be blinding in name only, and it
    would put back exactly the priming the pseudonyms were introduced to remove.

    Longest name first, so a name that contains another is not half-replaced. Names
    shorter than three characters are left alone: replacing them would corrupt
    unrelated text far more often than it would hide anything.
    """
    for name, pseudonym in name_map:
        if len(name) < 3:
            continue
        text = text.replace(name, pseudonym)
    return text


def _observed_facts(card: Scorecard, name_map: Sequence[tuple[str, str]] = ()) -> tuple[str, str]:
    """Render the facts a practitioner judges, and the evidence references behind them.

    Three deliberate choices, each of which costs something:

    * **No rule id, title, severity or status.** A rule id is a lookup key into
      ``docs/RULES.md``, where the severity is published; handing over the id
      therefore hands over the cap, and the cap *is* the verdict. The cost is that
      a labeler cannot cite "SEM-011" in a rationale. Rationales cite the fact.
    * **Lines sorted alphabetically, not in catalogue order.** Catalogue order is a
      second route back to the rule that produced each line.
    * **Unobserved evidence is collapsed into one trailing line.** A practitioner
      must know what could not be seen — hiding it would make the judgement
      uninformed, which is a worse failure than the residual leak. The residual leak
      is real and is accepted knowingly: a labeler who counts unobserved facts can
      approximate the tool's coverage. What they still cannot recover is the
      verdict, the score, or which checks passed.
    * **Facts derived from the engine's own verdict on another object are dropped.**
      ``assess()`` enriches a report with ``semantic_model_score`` and an agent with
      ``source_scores``, so a rule can legitimately report "source semantic model
      scores 11/100". That is not an observation — it is the tool's verdict one hop
      away, and on a sample that also contains the model it is the verdict itself.
      The test is generic rather than rule-specific: a score is by definition an
      engine output, so any observed key or detail that quotes one is excluded,
      along with its evidence reference.

    ``NOT_APPLICABLE`` outcomes are omitted entirely: out of scope is nothing to
    judge, and listing them would invite a labeler to read scope as a gap.
    """
    lines: set[str] = set()
    unobserved: set[str] = set()
    references: set[str] = set()

    for finding in card.findings:
        outcome = finding.outcome
        if outcome.status is RuleStatus.NOT_APPLICABLE:
            continue
        if _quotes_a_verdict(outcome.detail, outcome.observed):
            continue
        for item in outcome.evidence:
            if item.source or item.reference:
                references.add(f"{item.source}:{item.reference}")
        if outcome.status is RuleStatus.NOT_EVALUATED:
            keys = outcome.observed.get("missing_keys")
            if isinstance(keys, list) and keys:
                unobserved.update(str(key) for key in keys)
            else:
                unobserved.add("(evidence unavailable)")
            continue
        detail = re.sub(r"\s+", " ", outcome.detail or "").strip()
        measured = {
            key: value
            for key, value in sorted(outcome.observed.items())
            if key != "missing_keys" and value not in (None, [], {}, "")
        }
        if measured:
            rendered = ", ".join(f"{key}={_trim(value)}" for key, value in measured.items())
            detail = f"{detail} [{rendered}]" if detail else rendered
        if detail:
            lines.add(detail)

    facts = sorted(lines, key=str.casefold)
    if unobserved:
        facts.append("not observed: " + ", ".join(sorted(unobserved)))
    return (
        _pseudonymise("\n".join(facts), name_map),
        _pseudonymise("; ".join(sorted(references)), name_map),
    )


def _stratified_select(
    pool: Sequence[Scorecard],
    size: int,
    rng: random.Random,
) -> list[Scorecard]:
    """Draw ``size`` objects spread across ``(object_type, band)`` strata.

    Round-robin over the strata, each stratum shuffled by the seeded generator.
    A sample that is all semantic models, or all healthy objects, would tell a
    reader nothing about whether the thresholds hold across the estate, and it
    would be indistinguishable from cherry-picking. Selection is stratified by
    band on purpose; the band never leaves the key file.
    """
    buckets: dict[tuple[str, str], list[Scorecard]] = {}
    for card in pool:
        buckets.setdefault((card.object_type.value, _band(card)), []).append(card)
    for members in buckets.values():
        members.sort(key=lambda c: c.object_id)
        rng.shuffle(members)

    order = sorted(buckets)
    selected: list[Scorecard] = []
    while len(selected) < size and any(buckets[key] for key in order):
        for key in order:
            if len(selected) >= size:
                break
            if buckets[key]:
                selected.append(buckets[key].pop())
    return selected


def build_worksheet(
    run: AssessmentRun,
    *,
    size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> Worksheet:
    """Draw a reproducible, stratified, blinded calibration sample from ``run``.

    **Names are pseudonymised, always, with no opt-out.** "Legacy Marketing
    Dashboard", "Churn Sandbox" and "FIN_PNL_CONSO" each pre-load a verdict before
    a single fact is read, and a name is simultaneously the most identifying field
    in the sample — so pseudonymisation serves the blinding *and* the
    de-identification the roadmap's risk table requires, in one move. The real
    names live in the key file, which the coordinator keeps; a practitioner who
    genuinely needs to open the object asks the coordinator, and that request is
    then a recorded, deliberate act rather than an accident of the format.

    Row order is a seeded shuffle, and pseudonym ordinals are assigned from that
    same shuffle. Sorting rows by score would hand the labeler the ranking, which
    is most of the verdict; numbering them in score order would do the same thing
    one column to the left.
    """
    if size < 1:
        raise ScoringError(f"calibration sample size must be at least 1, got {size}")
    pool = sorted(run.scorecards, key=lambda c: (c.object_type.value, c.object_id))
    if not pool:
        raise ScoringError("assessment run has no scorecards to calibrate against")

    # One shuffle assigns every object in the estate a stable pseudonym, so a
    # sampled child can name its parent without either name appearing.
    naming_rng = random.Random(seed)
    shuffled = list(pool)
    naming_rng.shuffle(shuffled)
    counters: dict[str, int] = {}
    label_by_id: dict[str, str] = {}
    pseudonyms: dict[str, dict[str, str]] = {}
    for card in shuffled:
        code = TYPE_CODE.get(card.object_type, "OB")
        counters[code] = counters.get(code, 0) + 1
        label = f"{code}-{counters[code]:02d}"
        label_by_id[card.object_id] = label
        pseudonyms[label] = {
            "object_id": card.object_id,
            "object_name": card.object_name,
            "object_type": card.object_type.value,
        }

    selection_rng = random.Random(seed + 1)
    selected = _stratified_select(pool, size, selection_rng)
    row_rng = random.Random(seed + 2)
    row_rng.shuffle(selected)

    # Longest first so a name containing another ("Contoso-Dev" / "Contoso") is
    # replaced whole rather than half. Ids travel with names: an object id is as
    # identifying as a name and appears inside measured values such as
    # ``source_scores``.
    name_map = sorted(
        (
            (text, label_by_id[card.object_id])
            for card in pool
            for text in (card.object_name, card.object_id)
            if text
        ),
        key=lambda pair: (-len(pair[0]), pair[0]),
    )

    rows: list[WorksheetRow] = []
    key: list[KeyEntry] = []
    strata: dict[str, int] = {}
    for card in selected:
        label = label_by_id[card.object_id]
        parent_label = label_by_id.get(card.parent_id, "")
        facts, references = _observed_facts(card, name_map)
        rows.append(
            WorksheetRow(
                label=label,
                object_type=card.object_type.value,
                parent_label=parent_label,
                observed_facts=facts,
                evidence_references=references,
            )
        )
        band = _band(card)
        stratum = f"{card.object_type.value}/{band}"
        strata[stratum] = strata.get(stratum, 0) + 1
        key.append(
            KeyEntry(
                label=label,
                object_id=card.object_id,
                object_name=card.object_name,
                object_type=card.object_type.value,
                parent_label=parent_label,
                band=band,
                tool_status=card.status.value,
                tool_label=TOOL_STATUS_AS_LABEL[card.status].value,
                score=card.score,
                raw_score=card.raw_score,
                eligible=card.eligible,
                confidence=card.confidence,
                coverage=card.coverage,
            )
        )

    notes: list[str] = []
    low, high = ROADMAP_SAMPLE_BOUNDS
    if not low <= len(rows) <= high:
        notes.append(
            f"sample of {len(rows)} object(s) is outside the roadmap's {low}-{high} band "
            f"(pool held {len(pool)} object(s))"
        )
    if len(rows) < size:
        notes.append(f"requested {size} object(s); the run only contains {len(pool)}")

    worksheet = Worksheet(
        run_id=run.run_id,
        ruleset_version=run.ruleset_version or RULESET_VERSION,
        seed=seed,
        requested_size=size,
        rows=rows,
        key=key,
        strata=dict(sorted(strata.items())),
        pseudonyms=pseudonyms,
        notes=notes,
    )
    assert_blinded(worksheet)
    return worksheet


def assert_blinded(worksheet: Worksheet) -> None:
    """Raise unless the worksheet rows carry no trace of the tool's verdict.

    Called on every build, not only from the tests. A blinding guarantee that is
    only checked in a test file is a guarantee about the test file.

    Two independent checks, because either alone fails open:

    1. **Structural** — no row field is named in :data:`BLINDED_FIELDS`.
    2. **Value-level** — no cell reproduces the object's name, its score or raw score
       (rendered to one or two decimals, the way every report prints them), its
       confidence or coverage as serialised by ``Scorecard.to_dict`` (four
       decimals), or any word the engine publishes a verdict with.

    The value-level check on confidence and coverage is deliberately narrow. Both
    are ratios in ``[0, 1]``, and a measured fact legitimately reads "12/12 critical
    answers correct (100%)" — matching every two-decimal or percentage rendering
    would fail the build on a fact rather than a leak. Four decimals is the form a
    leak would actually take (a serialised scorecard field pasted into a cell) and
    is not a form any rule writes prose in. The structural check is what guarantees
    those two fields cannot be present at all.
    """
    present = set(WORKSHEET_COLUMNS) & BLINDED_FIELDS
    if present:
        raise ScoringError(f"worksheet columns leak verdict fields: {sorted(present)}")

    by_label = {entry.label: entry for entry in worksheet.key}
    # Every name and id in the estate, not only the row's own: a sampled model can
    # quote a sibling workspace or a capacity, and a name that primes one row primes
    # it wherever it appears.
    estate_identifiers = {
        str(value)
        for entry in worksheet.pseudonyms.values()
        for value in (entry.get("object_name"), entry.get("object_id"))
        if value and len(str(value)) >= 3
    }
    for row in worksheet.rows:
        leaked = set(row.to_dict()) & BLINDED_FIELDS
        if leaked:
            raise ScoringError(f"worksheet row {row.label} leaks verdict fields: {sorted(leaked)}")
        entry = by_label.get(row.label)
        for column, value in row.to_dict().items():
            if not isinstance(value, str) or not value:
                continue
            for token, pattern in _TOKEN_PATTERNS:
                if pattern.search(value):
                    raise ScoringError(
                        f"worksheet row {row.label} column {column} contains the verdict "
                        f"term {token!r}"
                    )
            if _VERDICT_QUOTE.search(value):
                raise ScoringError(
                    f"worksheet row {row.label} column {column} quotes an engine score"
                )
            for identifier in estate_identifiers:
                if identifier in value:
                    raise ScoringError(
                        f"worksheet row {row.label} column {column} contains the object "
                        f"identifier {identifier!r}"
                    )
            if entry is None:
                continue
            for number in (entry.score, entry.raw_score):
                for rendered in (f"{number:.1f}", f"{number:.2f}"):
                    if rendered in value:
                        raise ScoringError(
                            f"worksheet row {row.label} column {column} reproduces the score"
                        )
            for ratio_value in (entry.confidence, entry.coverage):
                if f"{ratio_value:.4f}" in value:
                    raise ScoringError(
                        f"worksheet row {row.label} column {column} reproduces "
                        "confidence or coverage"
                    )


# ── writing ──────────────────────────────────────────────────────────────────

INSTRUCTIONS = """# Calibration worksheet — labelling protocol

Run `{run_id}` · ruleset `{ruleset_version}` · seed `{seed}` · {count} objects
generated {generated_at}

You are labelling **blinded** objects. The tool's score, status, eligibility,
confidence and coverage have been removed, and object names have been replaced by
stable pseudonyms such as `SM-07`. This is deliberate: the point of the exercise is
to find out where your judgement and the tool's arithmetic diverge, and that answer
is worthless if you have already seen the arithmetic.

## How to fill this in

1. Open `{worksheet}` in Excel (or any spreadsheet).
2. Read the `observed_facts` cell for each row. Those are the measured facts about
   the object. `not observed:` lists evidence that could not be collected.
3. Put one value from the vocabulary below in the **`readiness_label`** column.
4. Write one or two sentences in **`rationale`** — what decided it for you. The
   rationale is the part that makes a disagreement usable; a bare label tells the
   next reader nothing about *why* two experienced people diverged.
5. Save as CSV and return it. Name the file after yourself, e.g. `{run_id}-jsmith.csv`.

## Vocabulary

| Value | Means |
|---|---|
| `ready` | I would let an AI/Copilot workload depend on this object as it stands. |
| `ready_with_conditions` | Usable, with named conditions or caveats. |
| `remediation_required` | Not usable until specific work is done. |
| `not_ready` | Should not be depended on at all in its current state. |
| `insufficient_evidence` | The facts given do not let me judge this object. |

`insufficient_evidence` is **not** the bottom of the scale. It is off the scale. Use
it when you cannot see enough, never as a polite way of saying "bad". It is analysed
separately for exactly that reason.

## Protocol

- Label **independently**. Do not discuss rows with the other labeler(s) until every
  worksheet is returned. Two labelers who converged by conversation measure the
  conversation, not the judgement.
- Do not look at any assessment output, HTML report or mart for this run.
- Leave a row blank rather than guessing. A missing label is handled honestly; an
  invented one is not.
- If you need to inspect the real object behind a pseudonym, ask the coordinator.
  Doing so un-blinds that row, and the coordinator records it.

## What happens next

The returned worksheets are analysed by `fabric_iq.calibration.analyse`, which
reports agreement **between the labelers first**, then between each labeler and the
tool, and enumerates every disagreement object by object. The analysis proposes no
weight and no threshold. Any change to the scoring maths is a separate, human
decision with its own review and regression test.

**Privacy.** This worksheet and every file beside it are tenant-derived evidence.
They live in a git-ignored folder, are never committed, and are deleted when the
exercise closes.
"""


def write_worksheet(worksheet: Worksheet, destination: str = CALIBRATION_SINK_ROOT) -> dict[str, str]:
    """Write the blinded CSV, the instruction sheet and the un-blinded key.

    Returns the paths written, keyed by ``worksheet`` / ``instructions`` / ``key``.
    The key is written to the same git-ignored folder but is never part of the
    hand-out; keeping it beside the worksheet is what makes "hand over exactly one
    of these two files" a decision somebody has to make rather than a default.
    """
    assert_blinded(worksheet)
    os.makedirs(destination, exist_ok=True)
    stem = worksheet.run_id

    worksheet_path = os.path.join(destination, f"{stem}_calibration_worksheet.csv")
    with open(worksheet_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(WORKSHEET_COLUMNS), extrasaction="raise")
        writer.writeheader()
        for row in worksheet.rows:
            writer.writerow(row.to_dict())

    instructions_path = os.path.join(destination, f"{stem}_calibration_instructions.md")
    with open(instructions_path, "w", encoding="utf-8") as handle:
        handle.write(
            INSTRUCTIONS.format(
                run_id=worksheet.run_id,
                ruleset_version=worksheet.ruleset_version,
                seed=worksheet.seed,
                count=len(worksheet.rows),
                generated_at=worksheet.generated_at,
                worksheet=os.path.basename(worksheet_path),
            )
        )

    key_path = os.path.join(destination, f"{stem}_calibration_key.json")
    with open(key_path, "w", encoding="utf-8") as handle:
        json.dump(worksheet.key_to_dict(), handle, indent=2, ensure_ascii=False)

    return {"worksheet": worksheet_path, "instructions": instructions_path, "key": key_path}


# ── reading labels back ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class LabelSet:
    """One practitioner's returned worksheet."""

    labeler_id: str
    labels: dict[str, CalibrationLabel]
    rationales: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def is_constant(self) -> bool:
        return len(set(self.labels.values())) == 1 and len(self.labels) > 1


def read_labels(path: str, labeler_id: str | None = None) -> LabelSet:
    """Read a filled worksheet back.

    A blank ``readiness_label`` is a missing label, recorded and reported, never
    imputed. A non-blank label outside the vocabulary is recorded as a problem and
    excluded — loudly, because a 20-30 row sample cannot afford a silent drop.
    """
    identifier = labeler_id or os.path.splitext(os.path.basename(path))[0]
    labels: dict[str, CalibrationLabel] = {}
    rationales: dict[str, str] = {}
    problems: list[str] = []
    seen: set[str] = set()
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "label" not in reader.fieldnames:
                raise ConfigurationError(f"{path}: not a calibration worksheet (no 'label' column)")
            if "readiness_label" not in reader.fieldnames:
                raise ConfigurationError(f"{path}: worksheet has no 'readiness_label' column")
            for row in reader:
                unit = (row.get("label") or "").strip()
                if not unit:
                    continue
                if unit in seen:
                    problems.append(f"{identifier}: duplicate row for {unit}")
                seen.add(unit)
                raw = row.get("readiness_label") or ""
                try:
                    label = parse_label(raw)
                except ConfigurationError as exc:
                    problems.append(f"{identifier}/{unit}: {exc}")
                    continue
                rationale = (row.get("rationale") or "").strip()
                if rationale:
                    rationales[unit] = rationale
                if label is None:
                    problems.append(f"{identifier}/{unit}: no label supplied")
                    continue
                labels[unit] = label
    except OSError as exc:
        raise ConfigurationError(f"cannot read calibration labels from {path}: {exc}") from exc
    return LabelSet(labeler_id=identifier, labels=labels, rationales=rationales, problems=problems)


# ── agreement ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgreementResult:
    """One agreement measurement, with the honest answer when there isn't one."""

    statistic: str
    value: float | None
    units_compared: int
    raters: int
    percent_agreement: float | None
    undefined_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    label_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistic": self.statistic,
            "value": None if self.value is None else round(self.value, 4),
            "units_compared": self.units_compared,
            "raters": self.raters,
            "percent_agreement": (
                None if self.percent_agreement is None else round(self.percent_agreement, 4)
            ),
            "undefined_reason": self.undefined_reason,
            "warnings": list(self.warnings),
            "label_counts": dict(self.label_counts),
        }


def _difference_matrix(categories: Sequence[Any], marginals: dict[Any, float], metric: str):
    """Squared difference between two categories under ``nominal`` or ``ordinal``."""
    if metric == "nominal":
        return lambda c, k: 0.0 if c == k else 1.0
    ordered = list(categories)
    index = {category: position for position, category in enumerate(ordered)}

    def ordinal(c: Any, k: Any) -> float:
        # Krippendorff's ordinal metric: the distance between two ranks is the mass
        # of the categories lying between them, so a step across a sparsely used
        # category counts for less than a step across a common one.
        low, high = sorted((index[c], index[k]))
        between = sum(marginals[ordered[g]] for g in range(low, high + 1))
        return (between - (marginals[c] + marginals[k]) / 2.0) ** 2

    return ordinal


def krippendorff_alpha(
    units: dict[str, list[Any]],
    *,
    metric: str = "ordinal",
    category_order: Sequence[Any] | None = None,
) -> tuple[float | None, int, str]:
    """Krippendorff's alpha over ``unit -> [value per rater]``.

    Returns ``(alpha, units_compared, undefined_reason)``.

    **Why this statistic.** Plain percent agreement over-credits chance: on a sample
    where four objects in five are unhealthy, two labelers who both default to
    "not ready" agree 80% of the time while having demonstrated nothing. Cohen's
    kappa corrects for chance but is defined for exactly two raters and cannot
    tolerate a blank cell, and the realistic state of a returned worksheet is two
    or three raters with a handful of blanks. Krippendorff's alpha handles any
    number of raters, tolerates missing values by construction (a unit contributes
    through the raters who actually labelled it), and accepts a difference function
    — so with the ordinal metric, `ready` versus `ready_with_conditions` counts as a
    smaller disagreement than `ready` versus `not_ready`. Unweighted statistics
    refuse to make that distinction, and on an ordinal ladder that refusal is
    simply wrong.

    Alpha is reported raw, including negative values, which mean systematic
    disagreement rather than "zero agreement".

    Degenerate cases return ``None`` and a reason rather than a number:

    * no unit carries two or more values — nothing is comparable;
    * every value in the comparable set is identical — expected disagreement is
      zero, so alpha is 0/0. That is **unmeasurable agreement, not perfect
      agreement**, and reporting 1.0 there would be the single most flattering lie
      this module could tell.
    """
    if metric not in ("nominal", "ordinal"):
        raise ConfigurationError(f"unknown agreement metric: {metric!r}")

    pairable = {unit: list(values) for unit, values in units.items() if len(values) >= 2}
    if not pairable:
        return None, 0, "no unit carries two or more labels, so nothing is comparable"

    observed_categories = {value for values in pairable.values() for value in values}
    if category_order:
        categories = [c for c in category_order if c in observed_categories]
        categories += sorted(observed_categories.difference(categories), key=str)
    else:
        categories = sorted(observed_categories, key=str)

    # Coincidence matrix: o[c][k] counts every ordered pair of values within a unit,
    # weighted by 1/(m_u - 1) so a heavily-labelled unit does not dominate.
    coincidence: dict[tuple[Any, Any], float] = {}
    for values in pairable.values():
        weight = 1.0 / (len(values) - 1)
        for left, right in itertools.permutations(values, 2):
            coincidence[(left, right)] = coincidence.get((left, right), 0.0) + weight

    marginals = {category: 0.0 for category in categories}
    for (left, _right), amount in coincidence.items():
        marginals[left] += amount
    total = sum(marginals.values())
    if total <= 1.0:
        return None, len(pairable), "fewer than two comparable values in the whole sample"

    difference = _difference_matrix(categories, marginals, metric)
    observed = sum(
        amount * difference(left, right) for (left, right), amount in coincidence.items()
    )
    expected = sum(
        marginals[left] * marginals[right] * difference(left, right)
        for left in categories
        for right in categories
    )
    if expected <= 0.0:
        only = categories[0] if len(categories) == 1 else None
        reason = (
            f"every label in the comparable sample is {only!s}: expected disagreement is "
            "zero, so agreement is unmeasurable rather than perfect"
            if only is not None
            else "expected disagreement is zero, so alpha is undefined"
        )
        return None, len(pairable), reason

    alpha = 1.0 - (total - 1.0) * observed / expected
    return alpha, len(pairable), ""


def _percent_agreement(units: dict[str, list[Any]]) -> float | None:
    """Exact-match agreement over every within-unit rater pair. Chance-inflated."""
    agree = 0
    pairs = 0
    for values in units.values():
        for left, right in itertools.combinations(values, 2):
            pairs += 1
            agree += 1 if left == right else 0
    return agree / pairs if pairs else None


def _label_counts(units: dict[str, list[Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for values in units.values():
        for value in values:
            key = value.value if isinstance(value, Enum) else str(value)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _agreement(
    units: dict[str, list[Any]],
    *,
    statistic: str,
    metric: str,
    raters: int,
    category_order: Sequence[Any] | None,
    warnings: list[str],
) -> AgreementResult:
    if raters < 2:
        return AgreementResult(
            statistic=statistic,
            value=None,
            units_compared=0,
            raters=raters,
            percent_agreement=None,
            undefined_reason=(
                "agreement needs at least two independent labelers; "
                f"{raters} worksheet(s) were supplied"
            ),
            warnings=list(warnings),
        )
    alpha, compared, reason = krippendorff_alpha(
        units, metric=metric, category_order=category_order
    )
    return AgreementResult(
        statistic=statistic,
        value=alpha,
        units_compared=compared,
        raters=raters,
        percent_agreement=_percent_agreement({u: v for u, v in units.items() if len(v) >= 2}),
        undefined_reason=reason,
        warnings=list(warnings),
        label_counts=_label_counts(units),
    )


# ── disagreement enumeration ─────────────────────────────────────────────────

DISAGREEMENT_COLUMNS = (
    "unit",
    "object_type",
    "kind",
    "left_rater",
    "left_label",
    "right_rater",
    "right_label",
    "ordinal_distance",
    "left_rationale",
    "right_rationale",
)


@dataclass(frozen=True)
class Disagreement:
    """One object, two voices, two different answers.

    ``kind`` separates the two things a divergence can mean:

    * ``readiness`` — both sides judged the object and placed it on different rungs.
    * ``coverage`` — one side said "I cannot judge this from the evidence". That is
      a disagreement about the *blind spot*, not about the object's quality, and
      merging it into the readiness numbers would quietly rank
      ``insufficient_evidence`` as the worst rung on a ladder it is not on.
    """

    unit: str
    object_type: str
    kind: str
    left_rater: str
    left_label: str
    right_rater: str
    right_label: str
    ordinal_distance: int | None
    left_rationale: str = ""
    right_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {column: getattr(self, column) for column in DISAGREEMENT_COLUMNS}


def _disagreement(
    unit: str,
    object_type: str,
    left_rater: str,
    left: CalibrationLabel,
    right_rater: str,
    right: CalibrationLabel,
    rationales: dict[str, dict[str, str]],
) -> Disagreement | None:
    if left is right:
        return None
    off_ladder = (
        left is CalibrationLabel.INSUFFICIENT_EVIDENCE
        or right is CalibrationLabel.INSUFFICIENT_EVIDENCE
    )
    distance = (
        None if off_ladder else abs(ORDINAL_RANK[left] - ORDINAL_RANK[right])
    )
    return Disagreement(
        unit=unit,
        object_type=object_type,
        kind="coverage" if off_ladder else "readiness",
        left_rater=left_rater,
        left_label=left.value,
        right_rater=right_rater,
        right_label=right.value,
        ordinal_distance=distance,
        left_rationale=rationales.get(left_rater, {}).get(unit, ""),
        right_rationale=rationales.get(right_rater, {}).get(unit, ""),
    )


# ── the report ───────────────────────────────────────────────────────────────


@dataclass
class CalibrationReport:
    """Agreement, disagreement, and deliberately no recommendation."""

    run_id: str
    ruleset_version: str
    labelers: list[str]
    inter_rater: AgreementResult
    blind_spot_agreement: AgreementResult
    tool_agreement: dict[str, AgreementResult]
    disagreements: list[Disagreement]
    coverage_units: list[str]
    unlabelled_units: list[str]
    problems: list[str]
    generated_at: str = field(default_factory=utcnow)

    #: Frozen empty by construction and asserted in the tests. Calibration produces
    #: evidence for a human decision; a routine that also proposed the correction it
    #: measured would have inverted the entire point of the exercise.
    proposals: tuple[()] = ()

    @property
    def readiness_disagreements(self) -> list[Disagreement]:
        return [d for d in self.disagreements if d.kind == "readiness"]

    @property
    def coverage_disagreements(self) -> list[Disagreement]:
        return [d for d in self.disagreements if d.kind == "coverage"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ruleset_version": self.ruleset_version,
            "generated_at": self.generated_at,
            "labelers": list(self.labelers),
            # Reported first on purpose: if the practitioners do not agree with each
            # other, their disagreement with the tool says nothing about the tool.
            "inter_rater_agreement": self.inter_rater.to_dict(),
            "blind_spot_agreement": self.blind_spot_agreement.to_dict(),
            "tool_agreement": {k: v.to_dict() for k, v in sorted(self.tool_agreement.items())},
            "disagreement_counts": {
                "total": len(self.disagreements),
                "readiness": len(self.readiness_disagreements),
                "coverage": len(self.coverage_disagreements),
            },
            "disagreements": [d.to_dict() for d in self.disagreements],
            "units_any_rater_could_not_judge": list(self.coverage_units),
            "unlabelled_units": list(self.unlabelled_units),
            "problems": list(self.problems),
            "proposals": list(self.proposals),
            "proposals_note": (
                "Calibration records evidence. It proposes no weight, threshold, cap or "
                "rollup change; any such change is a separate human decision reviewed by "
                "@scorer with its own regression test in tests/test_scoring.py."
            ),
            "privacy": (
                "Tenant-derived calibration evidence: pseudonyms, practitioner labels and "
                "rationales. Git-ignored destination, never committed."
            ),
        }

    def to_json(self, path: str | None = None, indent: int = 2) -> str:
        payload = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
        return payload

    def disagreements_to_csv(self, path: str) -> str:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(DISAGREEMENT_COLUMNS))
            writer.writeheader()
            for item in self.disagreements:
                writer.writerow(item.to_dict())
        return path


def analyse(
    key: dict[str, Any] | str,
    label_sets: Iterable[LabelSet],
) -> CalibrationReport:
    """Compare returned worksheets with each other, then with the tool.

    ``key`` is the key file (a path or its parsed contents). Every returned unit
    must exist in the key; an unknown pseudonym is recorded as a problem rather
    than quietly analysed, because it usually means two runs got mixed.

    Ordering is not cosmetic. Inter-rater agreement comes first because it is the
    precondition for everything after it: if two practitioners cannot agree with
    each other, their disagreement with the tool measures the labelling exercise,
    not the scoring engine — and a report that leads with "the tool disagrees with
    the experts" would have inverted cause and effect.

    ``insufficient_evidence`` is held out of the ordinal comparison on both sides
    and analysed separately, twice: as a nominal "did the labelers agree about
    where the blind spots are" statistic over the whole sample, and as enumerated
    ``coverage`` disagreements. It is never ranked below ``not_ready``.
    """
    if isinstance(key, str):
        try:
            with open(key, encoding="utf-8") as handle:
                key_data = json.load(handle)
        except OSError as exc:
            raise ConfigurationError(f"cannot read calibration key {key}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"calibration key {key} is not valid JSON: {exc}") from exc
    else:
        key_data = dict(key)

    entries = {
        entry["label"]: KeyEntry.from_dict(entry)
        for entry in key_data.get("entries", [])
        if isinstance(entry, dict) and entry.get("label")
    }
    if not entries:
        raise ConfigurationError("calibration key contains no entries")

    sets = sorted(label_sets, key=lambda s: s.labeler_id)
    problems: list[str] = []
    for label_set in sets:
        problems.extend(label_set.problems)
        for unit in sorted(label_set.labels):
            if unit not in entries:
                problems.append(
                    f"{label_set.labeler_id}: {unit} is not in this calibration key"
                )
    if len({s.labeler_id for s in sets}) != len(sets):
        raise ConfigurationError("two label sets share a labeler id; results would be merged")

    known = {
        label_set.labeler_id: {
            unit: label for unit, label in label_set.labels.items() if unit in entries
        }
        for label_set in sets
    }
    rationales = {label_set.labeler_id: dict(label_set.rationales) for label_set in sets}

    # Inter-rater, ordinal: units where every contributing labeler placed the object
    # on the ladder. A unit only enters once at least two labelers judged it.
    ordinal_units: dict[str, list[CalibrationLabel]] = {}
    blind_spot_units: dict[str, list[str]] = {}
    coverage_units: list[str] = []
    for unit in sorted(entries):
        judged: list[CalibrationLabel] = []
        blind: list[str] = []
        for labeler in known:
            label = known[labeler].get(unit)
            if label is None:
                continue
            blind.append(
                "unjudgeable" if label is CalibrationLabel.INSUFFICIENT_EVIDENCE else "judgeable"
            )
            if label is CalibrationLabel.INSUFFICIENT_EVIDENCE:
                continue
            judged.append(label)
        if blind:
            blind_spot_units[unit] = blind
        if judged:
            ordinal_units[unit] = judged
        if any(
            known[labeler].get(unit) is CalibrationLabel.INSUFFICIENT_EVIDENCE for labeler in known
        ):
            coverage_units.append(unit)

    warnings: list[str] = []
    for labeler, labels in sorted(known.items()):
        if len(labels) > 1 and len(set(labels.values())) == 1:
            only = next(iter(labels.values())).value
            warnings.append(
                f"{labeler} used a single label ({only}) for all {len(labels)} labelled "
                "rows; agreement involving this labeler carries no information about "
                "discrimination"
            )
        missing = sorted(set(entries) - set(labels))
        if missing:
            warnings.append(f"{labeler} left {len(missing)} of {len(entries)} rows unlabelled")

    ladder = [
        CalibrationLabel.NOT_READY,
        CalibrationLabel.REMEDIATION_REQUIRED,
        CalibrationLabel.READY_WITH_CONDITIONS,
        CalibrationLabel.READY,
    ]
    inter_rater = _agreement(
        ordinal_units,
        statistic="krippendorff_alpha_ordinal",
        metric="ordinal",
        raters=len(sets),
        category_order=ladder,
        warnings=warnings,
    )
    blind_spot = _agreement(
        blind_spot_units,
        statistic="krippendorff_alpha_nominal_blind_spot",
        metric="nominal",
        raters=len(sets),
        category_order=["judgeable", "unjudgeable"],
        warnings=warnings,
    )

    tool_agreement: dict[str, AgreementResult] = {}
    for labeler, labels in sorted(known.items()):
        paired: dict[str, list[CalibrationLabel]] = {}
        for unit, label in sorted(labels.items()):
            if label is CalibrationLabel.INSUFFICIENT_EVIDENCE:
                continue
            tool_label = CalibrationLabel(entries[unit].tool_label)
            if tool_label is CalibrationLabel.INSUFFICIENT_EVIDENCE:
                continue
            paired[unit] = [label, tool_label]
        tool_agreement[labeler] = _agreement(
            paired,
            statistic="krippendorff_alpha_ordinal",
            metric="ordinal",
            raters=2,
            category_order=ladder,
            warnings=[],
        )

    # Every disagreement, enumerated. An aggregate that hides which object diverged
    # fails the roadmap's requirement outright: the rationale on the diverging row is
    # the only part of this exercise that can ever justify a change to the maths.
    disagreements: list[Disagreement] = []
    for unit in sorted(entries):
        object_type = entries[unit].object_type
        for left, right in itertools.combinations(sorted(known), 2):
            left_label = known[left].get(unit)
            right_label = known[right].get(unit)
            if left_label is None or right_label is None:
                continue
            item = _disagreement(
                unit, object_type, left, left_label, right, right_label, rationales
            )
            if item is not None:
                disagreements.append(item)
        tool_label = CalibrationLabel(entries[unit].tool_label)
        for labeler in sorted(known):
            label = known[labeler].get(unit)
            if label is None:
                continue
            item = _disagreement(
                unit, object_type, labeler, label, TOOL_RATER_ID, tool_label, rationales
            )
            if item is not None:
                disagreements.append(item)

    unlabelled = sorted(
        unit for unit in entries if not any(unit in labels for labels in known.values())
    )

    return CalibrationReport(
        run_id=str(key_data.get("run_id", "")),
        ruleset_version=str(key_data.get("ruleset_version", "")),
        labelers=[s.labeler_id for s in sets],
        inter_rater=inter_rater,
        blind_spot_agreement=blind_spot,
        tool_agreement=tool_agreement,
        disagreements=disagreements,
        coverage_units=coverage_units,
        unlabelled_units=unlabelled,
        problems=sorted(set(problems)),
    )


def write_report(
    report: CalibrationReport,
    destination: str = CALIBRATION_SINK_ROOT,
) -> dict[str, str]:
    """Write the agreement JSON and the enumerated-disagreement CSV."""
    os.makedirs(destination, exist_ok=True)
    stem = report.run_id or "calibration"
    agreement_path = os.path.join(destination, f"{stem}_calibration_agreement.json")
    report.to_json(agreement_path)
    disagreement_path = os.path.join(destination, f"{stem}_calibration_disagreements.csv")
    report.disagreements_to_csv(disagreement_path)
    return {"agreement": agreement_path, "disagreements": disagreement_path}


def summarise(report: CalibrationReport) -> str:
    """One console block: inter-rater first, then the tool, then every disagreement."""
    lines = [
        f"Calibration — run {report.run_id} (ruleset {report.ruleset_version})",
        f"  labelers: {', '.join(report.labelers) or 'none'}",
        "",
        "  Inter-rater agreement (read this first)",
        f"    {_format_agreement(report.inter_rater)}",
        f"    blind spots: {_format_agreement(report.blind_spot_agreement)}",
        "",
        "  Labeler vs tool",
    ]
    for labeler, result in sorted(report.tool_agreement.items()):
        lines.append(f"    {labeler}: {_format_agreement(result)}")
    lines.append("")
    lines.append(
        f"  Disagreements: {len(report.readiness_disagreements)} readiness, "
        f"{len(report.coverage_disagreements)} coverage"
    )
    for item in report.disagreements:
        distance = "" if item.ordinal_distance is None else f", {item.ordinal_distance} step(s)"
        lines.append(
            f"    {item.unit} [{item.object_type}] {item.left_rater}={item.left_label} "
            f"vs {item.right_rater}={item.right_label} ({item.kind}{distance})"
        )
    for warning in report.inter_rater.warnings:
        lines.append(f"  ! {warning}")
    for problem in report.problems:
        lines.append(f"  ! {problem}")
    lines.append("")
    lines.append("  This report proposes no weight, threshold or cap change, by design.")
    return "\n".join(lines)


def _format_agreement(result: AgreementResult) -> str:
    if result.value is None:
        return f"{result.statistic}: undefined — {result.undefined_reason}"
    percent = (
        "" if result.percent_agreement is None else f", exact match {result.percent_agreement:.0%}"
    )
    return (
        f"{result.statistic} = {result.value:.3f} over {result.units_compared} unit(s), "
        f"{result.raters} rater(s){percent}"
    )


__all__ = [
    "CALIBRATION_SINK_ROOT",
    "CALIBRATION_ARTIFACTS",
    "BLINDED_FIELDS",
    "DEFAULT_SAMPLE_SIZE",
    "DEFAULT_SEED",
    "ROADMAP_SAMPLE_BOUNDS",
    "AgreementResult",
    "CalibrationLabel",
    "CalibrationReport",
    "Disagreement",
    "KeyEntry",
    "LabelSet",
    "Worksheet",
    "WorksheetRow",
    "analyse",
    "assert_blinded",
    "build_worksheet",
    "calibration_sinks",
    "krippendorff_alpha",
    "parse_label",
    "read_labels",
    "summarise",
    "write_report",
    "write_worksheet",
]
