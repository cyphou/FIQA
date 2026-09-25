"""Fabric IQ Readiness Assessor.

Evaluates whether a Power BI / Microsoft Fabric tenant and its objects
(workspaces, semantic models, reports, Fabric Data Agents) are ready for
Fabric IQ and agentic experiences.

The package is read-only by design: it collects evidence, applies versioned
rules, produces explainable scores, and emits a remediation backlog. It never
modifies the evaluated tenant.
"""

__version__ = "0.1.0"

#: Version of the rule catalogue and scoring constants. It is the only
#: comparability key a stored run carries: two runs may be compared **only** if
#: they stamp the same value. It must be incremented whenever
#: ``fabric_iq.scoring.ruleset_fingerprint()`` changes, and every published
#: value must have an entry in ``fabric_iq.scoring.RULESET_HISTORY``.
#: `tests/test_scoring.py` enforces both. See docs/SCORING.md
#: "Ruleset Versioning" before changing this line.
RULESET_VERSION = "2026.09.2"

__all__ = ["__version__", "RULESET_VERSION"]
