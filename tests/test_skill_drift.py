"""The agent-facing Skill must not drift from the engine constants.

`.github/skills/fabric-iq-readiness/SKILL.md` is read by a model as authoritative
instruction at prompt time. It restates, as prose literals, limits and thresholds
that the engine owns as named constants. `docs/RULES.md` is generated and
CI-checked; the Skill is hand-written, so nothing but this module stands between a
changed constant and a model confidently quoting last release's number.

The claims are asserted by *shape*, not by substring: each pattern matches the
sentence that carries the claim with the number captured, and every occurrence of
that sentence must carry the value the engine holds. Asserting that "5" appears
somewhere in the file would pass even if the Skill also said six.

Relationship to ``ruleset_fingerprint()``
-----------------------------------------
``fabric_iq.scoring.ruleset_fingerprint()`` and ``RULESET_HISTORY`` bind the
*engine* to the *ledger*: the compiled catalogue cannot move under a fixed
``RULESET_VERSION`` token (``test_scoring.py``). This module binds the *prose* to
the *engine*. They meet at one authority and never restate each other: every
expected value here is read from the live registry and the live constants, never
from ``current_release().rule_count``, which the fingerprint guard already pins to
that same registry. One fact, one chain: registry -> ledger, registry -> Skill.

The catalogue-size and version claims mirror what ``assess.py --list-rules``
prints (``f"Ruleset {RULESET_VERSION} - {len(registry)} rules"``), because that
command is what the Skill tells a reconciler to run.
"""

import os
import re
import unittest

from fabric_iq import RULESET_VERSION
from fabric_iq.models import SEVERITY_SCORE_CAP, ObjectType, RuleStatus, Severity
from fabric_iq.rules import registry
from fabric_iq.rules.data_agent_rules import (
    MAX_DATA_SOURCES,
    MAX_RESULT_COLUMNS,
    MAX_RESULT_ROWS,
    MIN_ACCURACY,
    MIN_CRITICAL_ACCURACY,
)
from fabric_iq.rules.semantic_model_rules import AI_INSTRUCTIONS_MAX, DESCRIPTION_BUDGET
from fabric_iq.rules.tenant_rules import ELIGIBLE_FABRIC_SKUS, ELIGIBLE_PREMIUM_SKUS
from fabric_iq.scoring import MIN_COVERAGE_TO_PUBLISH
from tests.helpers import REPO_ROOT

SKILL_PATH = os.path.join(
    REPO_ROOT, ".github", "skills", "fabric-iq-readiness", "SKILL.md"
)


def skill_text():
    """The Skill with runs of whitespace flattened, so a wrapped claim still reads."""
    with open(SKILL_PATH, encoding="utf-8") as handle:
        return re.sub(r"\s+", " ", handle.read())


def _percent(fraction):
    """A fraction as the whole-number percentage the Skill prints."""
    return str(round(fraction * 100))


def _lowest_sku(skus):
    """The floor of a SKU family, e.g. {'F64','F2','F8'} -> 'F2'."""
    return min(skus, key=lambda sku: int(sku[1:]))


_B = r"\*{0,2}"  # optional bold markers around a stated value

#: claim name -> (sentence pattern with one group per value, expected values).
#: The expected values are derived from the imported constants; nothing here
#: duplicates a threshold. Thousands separators and bold markers are tolerated,
#: so the Skill may write 10,000 or **10000** -- but never a different number.
CLAIMS = {
    "MAX_DATA_SOURCES": (
        rf"at most {_B}(\d[\d,]*) data sources",
        (str(MAX_DATA_SOURCES),),
    ),
    "MAX_RESULT_ROWS x MAX_RESULT_COLUMNS": (
        rf"read-only {_B}(\d[\d,]*) ?[x\u00d7] ?(\d[\d,]*){_B} result surface",
        (str(MAX_RESULT_ROWS), str(MAX_RESULT_COLUMNS)),
    ),
    "DESCRIPTION_BUDGET": (
        rf"first {_B}(\d[\d,]*) characters{_B} carry the meaning",
        (str(DESCRIPTION_BUDGET),),
    ),
    "AI_INSTRUCTIONS_MAX": (
        rf"AI instructions within {_B}(\d[\d,]*) characters",
        (str(AI_INSTRUCTIONS_MAX),),
    ),
    "MIN_ACCURACY": (
        rf"\u2265 ?{_B}(\d+)%{_B} accuracy",
        (_percent(MIN_ACCURACY),),
    ),
    "MIN_CRITICAL_ACCURACY": (
        rf"\u2265 ?{_B}(\d+)%{_B} on critical questions",
        (_percent(MIN_CRITICAL_ACCURACY),),
    ),
    "blocking cap (prose)": (
        rf"blocking failure caps the score at {_B}(\d+)",
        (f"{SEVERITY_SCORE_CAP[Severity.BLOCKING]:.0f}",),
    ),
    "blocking cap (triage table)": (
        rf"Score (?:[\u2264<=] ?)?{_B}(\d+){_B}, eligible = false",
        (f"{SEVERITY_SCORE_CAP[Severity.BLOCKING]:.0f}",),
    ),
    "major cap": (
        rf"major failure caps (?:the score )?at {_B}(\d+)",
        (f"{SEVERITY_SCORE_CAP[Severity.MAJOR]:.0f}",),
    ),
    "MIN_COVERAGE_TO_PUBLISH": (
        rf"[Cc]overage below {_B}(\d+)%",
        (_percent(MIN_COVERAGE_TO_PUBLISH),),
    ),
    # The catalogue size is stated twice, in two different wordings: once as the
    # comment on the `--list-rules` command, once in the reconciliation footer as
    # the output that command produced. The footer is not a second copy of the
    # first sentence, so a pattern written for one does NOT see the other -- which
    # is how a count goes stale in the half the gate cannot read. Both are claimed,
    # and `test_every_rule_count_statement_is_claimed` below fails if a third
    # wording appears.
    "rule catalogue size (--list-rules comment)": (
        rf"catalogue: {_B}(\d[\d,]*) rules",
        (str(len(registry)),),
    ),
    "rule catalogue size (reconciliation footer)": (
        rf"\u2014 ?{_B}(\d[\d,]*) rules",
        (str(len(registry)),),
    ),
    # A stale version token is worse than a stale number: RULESET_HISTORY exists
    # because one token standing for two catalogues destroys comparability, and a
    # model quoting last release's token from here reproduces exactly that.
    "RULESET_VERSION": (
        rf"[Rr]uleset `?{_B}(\d{{4}}\.\d{{2}}\.\d+)",
        (RULESET_VERSION,),
    ),
    "eligible capacity floor": (
        rf"{_B}(F\d+)\+ ?/ ?(P\d+)\+",
        (_lowest_sku(ELIGIBLE_FABRIC_SKUS), _lowest_sku(ELIGIBLE_PREMIUM_SKUS)),
    ),
}

#: Any sentence anywhere in the Skill that states a catalogue size or a ruleset
#: token, regardless of wording. Used to prove the CLAIMS patterns above see
#: *every* statement of those two facts, not merely the ones they were written
#: for. A gate that reads one of two statements is the defect, not the fix.
COUNT_ANYWHERE = rf"{_B}(\d[\d,]*) rules"
VERSION_ANYWHERE = r"(\d{4}\.\d{2}\.\d+)"

#: Claims whose pattern must jointly account for every occurrence above.
COUNT_CLAIMS = (
    "rule catalogue size (--list-rules comment)",
    "rule catalogue size (reconciliation footer)",
)
VERSION_CLAIMS = ("RULESET_VERSION",)


def matches(text, pattern):
    """Every occurrence of a claim sentence, each as a tuple of captured values."""
    found = re.findall(pattern, text)
    return [
        tuple(v.replace(",", "") for v in (m if isinstance(m, tuple) else (m,)))
        for m in found
    ]


class TestSkillStatesTheEngineValues(unittest.TestCase):
    def test_the_skill_exists(self):
        self.assertTrue(os.path.exists(SKILL_PATH), f"missing Skill: {SKILL_PATH}")

    def test_every_claim_sentence_is_present(self):
        text = skill_text()
        for name, (pattern, _expected) in CLAIMS.items():
            with self.subTest(claim=name):
                self.assertTrue(
                    matches(text, pattern),
                    f"SKILL.md no longer states the {name} claim in the expected "
                    f"wording; the drift check cannot see it (pattern: {pattern})",
                )

    def test_every_stated_value_equals_the_engine_constant(self):
        text = skill_text()
        for name, (pattern, expected) in CLAIMS.items():
            for occurrence in matches(text, pattern):
                with self.subTest(claim=name, stated=occurrence):
                    self.assertEqual(
                        occurrence,
                        expected,
                        f"SKILL.md states {occurrence} for {name} but the engine "
                        f"holds {expected}; update the Skill (@readme) or the "
                        f"constant, never only one",
                    )

    def test_every_rule_count_statement_is_claimed(self):
        """No sentence may state the catalogue size outside a claimed wording."""
        text = skill_text()
        claimed = sum(
            len(matches(text, CLAIMS[name][0])) for name in COUNT_CLAIMS
        )

        self.assertEqual(
            len(matches(text, COUNT_ANYWHERE)),
            claimed,
            "SKILL.md states the catalogue size in a wording no CLAIMS pattern "
            "matches, so that statement is ungated and can go stale silently. "
            "Add a claim for the new wording (@tester) or keep the existing one.",
        )

    def test_every_ruleset_version_literal_is_claimed(self):
        """Same, for the ruleset token."""
        text = skill_text()
        claimed = sum(
            len(matches(text, CLAIMS[name][0])) for name in VERSION_CLAIMS
        )

        self.assertEqual(
            len(matches(text, VERSION_ANYWHERE)),
            claimed,
            "SKILL.md prints a ruleset version in a wording no CLAIMS pattern "
            "matches; an unreadable version literal is how a model ends up "
            "quoting a token that no longer identifies this catalogue",
        )


#: The sentence naming the rules that go silent when an agent carries no
#: evaluation block. Captured as a region so the IDs can be compared as a *set*
#: against the engine: this claim was wrong in exactly the way a count cannot be
#: -- it named a contiguous range and silently omitted a rule outside it, so an
#: agent quoting it would have reported AGT-014's silence as a defect.
UNEVALUABLE_SENTENCE = rf"without it (.*?) returns? {_B}`?NOT_EVALUATED"

_ID_OR_ELLIPSIS = r"AGT-\d+|\u2026|\.\.\."


def _agent_with_evaluation(**overrides):
    """A Data Agent subject complete enough that no AGT rule is unevaluable.

    Built here rather than imported from another test module or read from
    `examples/sample_tenant` (owned by @collector): the claim under test is about
    the *evaluation block alone*, so the basis must be a subject where nothing
    else is missing. `test_the_basis_subject_leaves_nothing_unevaluated` proves
    that property instead of assuming it.
    """

    subject = {
        "id": "agt-drift",
        "name": "Drift Probe Agent",
        "parent_id": "ws-drift",
        "data_sources": [
            {
                "id": "sm-drift",
                "name": "Drift Probe Model",
                "type": "semantic_model",
                "reachable": True,
                "description": "Commercial questions about the synthetic estate.",
            }
        ],
        "source_scores": {"sm-drift": 92.0},
        "instructions": "Answer sales questions only. " * 12,
        "target_languages": ["fr"],
        "requires_write": False,
        "expects_bulk_export": False,
        "latency_sla_seconds": 30,
        "preview_dependencies": [],
        "evaluation": {
            "questions_asked": 30,
            "executable_queries": 29,
            "correct_answers": 28,
            "critical_questions_asked": 5,
            "critical_questions_correct": 5,
            "personas_tested": 3,
            "leakage_incidents": 0,
            "negative_tests": 5,
            "negative_tests_refused": 5,
            "languages_tested": ["fr"],
            "latency_p95_seconds": 12,
        },
    }
    subject.update(overrides)
    return subject


def _unevaluable_without_an_evaluation_block():
    """Rule IDs the engine cannot evaluate when the evaluation block is absent."""
    subject = _agent_with_evaluation()
    del subject["evaluation"]
    return {
        rule.id
        for rule in registry.for_type(ObjectType.DATA_AGENT)
        if rule.evaluate(subject).status is RuleStatus.NOT_EVALUATED
    }


def expand_rule_ids(region, known):
    """The rule IDs a prose region names, expanding `AGT-006 ... AGT-012` ranges.

    ``known`` is the set of IDs that actually exist, so a range means the rules a
    reader would take it to mean rather than every integer in between.
    """

    def number(rule_id):
        return int(rule_id.split("-")[1])

    named, ranged = [], False
    for token in re.findall(_ID_OR_ELLIPSIS, region):
        if token in ("\u2026", "..."):
            if not named:
                raise ValueError(f"range with no lower bound in {region!r}")
            ranged = True
            continue
        if ranged:
            low, high = number(named[-1]), number(token)
            named.extend(
                sorted(
                    (r for r in known if low < number(r) <= high), key=number
                )
            )
            ranged = False
        else:
            named.append(token)
    if ranged:
        raise ValueError(f"range with no upper bound in {region!r}")
    return set(named)


class TestSkillNamesTheAgentRulesThatNeedAnEvaluationBlock(unittest.TestCase):
    """`AGT-006 ... AGT-012` **and `AGT-014`** must be exactly the silent set.

    Unlike a threshold, this claim cannot be checked against a constant -- it is a
    property of the rules' behaviour, so it is derived by running them. It is
    gated because it is the claim that was false: a reader told that AGT-014 is
    not in the set concludes its `NOT_EVALUATED` is a defect to chase.
    """

    def setUp(self):
        self.known = {rule.id for rule in registry.for_type(ObjectType.DATA_AGENT)}

    def region(self):
        found = re.findall(UNEVALUABLE_SENTENCE, skill_text())
        self.assertTrue(
            found,
            "SKILL.md no longer states which rules return NOT_EVALUATED without an "
            f"evaluation block in the expected wording (pattern: {UNEVALUABLE_SENTENCE})",
        )
        self.assertEqual(len(found), 1, f"the claim is stated more than once: {found}")
        return found[0]

    def test_the_basis_subject_leaves_nothing_unevaluated(self):
        """Otherwise the set below would include rules missing for other reasons."""
        subject = _agent_with_evaluation()
        silent = [
            rule.id
            for rule in registry.for_type(ObjectType.DATA_AGENT)
            if rule.evaluate(subject).status is RuleStatus.NOT_EVALUATED
        ]

        self.assertEqual(silent, [], "the probe subject is incomplete for other rules")

    def test_every_named_rule_exists(self):
        named = expand_rule_ids(self.region(), self.known)

        self.assertTrue(named, "the claim sentence names no rule at all")
        self.assertLessEqual(
            named,
            self.known,
            "SKILL.md names a Data Agent rule that is not in the catalogue",
        )

    def test_the_named_set_is_exactly_what_the_engine_cannot_evaluate(self):
        named = expand_rule_ids(self.region(), self.known)
        actual = _unevaluable_without_an_evaluation_block()

        self.assertEqual(
            named,
            actual,
            "\nSKILL.md names the wrong set of rules as unevaluable without an "
            "evaluation block.\n"
            f"  stated:  {sorted(named)}\n"
            f"  engine:  {sorted(actual)}\n"
            f"  missing from the Skill: {sorted(actual - named)}\n"
            f"  claimed but evaluable:  {sorted(named - actual)}\n"
            "A rule missing from that list is reported to a user as a defect to "
            "chase; a rule wrongly in it hides a real failure. Update the Skill "
            "(@readme) or the rules (@data-agent), never only one.",
        )


class TestTheDriftCheckActuallyDetectsDrift(unittest.TestCase):
    """A drift check that cannot fail is decoration.

    These exercise the comparison against synthetic text: a Skill that quotes a
    stale number, and a Skill that quotes both the right and a contradictory one.
    """

    def test_a_stale_value_is_caught(self):
        pattern, expected = CLAIMS["MAX_DATA_SOURCES"]
        stale = f"at most **{MAX_DATA_SOURCES + 1} data sources**, all reachable"

        self.assertNotEqual(matches(stale, pattern), [expected])

    def test_a_contradictory_second_statement_is_caught(self):
        pattern, expected = CLAIMS["MAX_DATA_SOURCES"]
        text = (
            f"at most **{MAX_DATA_SOURCES} data sources**. "
            f"Later: at most **{MAX_DATA_SOURCES + 3} data sources**."
        )
        occurrences = matches(text, pattern)

        self.assertEqual(len(occurrences), 2)
        self.assertIn(expected, occurrences)
        self.assertNotEqual(occurrences, [expected, expected])

    def test_a_wrapped_claim_still_reads(self):
        pattern, expected = CLAIMS["AI_INSTRUCTIONS_MAX"]
        wrapped = re.sub(
            r"\s+", " ", f"AI instructions within **{AI_INSTRUCTIONS_MAX:,}\ncharacters**"
        )

        self.assertEqual(matches(wrapped, pattern), [expected])

    def test_a_stale_catalogue_size_is_caught_in_both_wordings(self):
        stale = len(registry) - 2  # the drift that actually happened: 65 for 67
        for name in COUNT_CLAIMS:
            pattern, expected = CLAIMS[name]
            with self.subTest(claim=name):
                text = f"catalogue: {stale} rules \u2014 {stale} rules"

                self.assertTrue(matches(text, pattern), "pattern reads neither wording")
                self.assertNotIn(expected, matches(text, pattern))

    def test_a_footer_count_is_not_read_by_the_command_comment_pattern(self):
        """Why two claims and not one: the wordings do not see each other."""
        comment_pattern = CLAIMS["rule catalogue size (--list-rules comment)"][0]
        footer_only = f"reported `Ruleset {RULESET_VERSION} \u2014 {len(registry)} rules`"

        self.assertEqual(matches(footer_only, comment_pattern), [])
        self.assertEqual(
            matches(footer_only, CLAIMS["rule catalogue size (reconciliation footer)"][0]),
            [(str(len(registry)),)],
        )

    def test_a_stale_ruleset_token_is_caught(self):
        pattern, expected = CLAIMS["RULESET_VERSION"]

        self.assertNotIn(expected, matches("encoded by ruleset `1999.01.1`", pattern))

    def test_an_omitted_rule_id_is_caught(self):
        """The `AGT-014` defect, reproduced against the comparison itself."""
        known = {rule.id for rule in registry.for_type(ObjectType.DATA_AGENT)}
        actual = _unevaluable_without_an_evaluation_block()

        omitted = expand_rule_ids("`AGT-006` \u2026 `AGT-012`", known)
        corrected = expand_rule_ids("`AGT-006` \u2026 `AGT-012` and `AGT-014`", known)

        self.assertNotEqual(omitted, actual)
        self.assertEqual(corrected, actual)
        self.assertEqual(omitted, actual - {"AGT-014"})

    def test_an_over_claimed_rule_id_is_caught(self):
        known = {rule.id for rule in registry.for_type(ObjectType.DATA_AGENT)}
        actual = _unevaluable_without_an_evaluation_block()

        over = expand_rule_ids("`AGT-005` \u2026 `AGT-012` and `AGT-014`", known)

        self.assertNotEqual(over, actual)
        self.assertEqual(over - actual, {"AGT-005"})


if __name__ == "__main__":
    unittest.main()
