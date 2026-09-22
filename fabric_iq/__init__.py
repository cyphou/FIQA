"""Fabric IQ Readiness Assessor.

Evaluates whether a Power BI / Microsoft Fabric tenant and its objects
(workspaces, semantic models, reports, Fabric Data Agents) are ready for
Fabric IQ and agentic experiences.

The package is read-only by design: it collects evidence, applies versioned
rules, produces explainable scores, and emits a remediation backlog. It never
modifies the evaluated tenant.
"""

__version__ = "0.1.0"

RULESET_VERSION = "2026.09.1"

__all__ = ["__version__", "RULESET_VERSION"]
