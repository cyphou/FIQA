"""Versioned rule catalogue for Fabric IQ readiness.

A rule is a pure function over one normalized inventory object. Rules never
call an API and never mutate the subject, so a run is reproducible from the
Bronze evidence alone.
"""

from fabric_iq.rules.base import Rule, RuleRegistry, registry
from fabric_iq.rules import (  # noqa: F401  (import for registration side effects)
    data_agent_rules,
    report_rules,
    semantic_model_rules,
    tenant_rules,
    workspace_rules,
)

__all__ = ["Rule", "RuleRegistry", "registry"]
