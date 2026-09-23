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
"""

import os
import re
import unittest

from fabric_iq.models import SEVERITY_SCORE_CAP, Severity
from fabric_iq.rules.data_agent_rules import (
    MAX_DATA_SOURCES,
    MAX_RESULT_COLUMNS,
    MAX_RESULT_ROWS,
    MIN_ACCURACY,
    MIN_CRITICAL_ACCURACY,
)
from fabric_iq.rules.semantic_model_rules import AI_INSTRUCTIONS_MAX, DESCRIPTION_BUDGET
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
}


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


if __name__ == "__main__":
    unittest.main()
