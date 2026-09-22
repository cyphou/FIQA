"""Domain exception hierarchy for the Fabric IQ readiness assessor.

Every new failure path raises one of these instead of a bare ValueError or
RuntimeError, so resilience boundaries can catch AssessmentError without
swallowing genuine defects.
"""


class AssessmentError(Exception):
    """Base class for every error raised by this package."""


class CollectionError(AssessmentError):
    """Raised when evidence collection fails (API, auth, throttling, IO)."""


class ThrottlingError(CollectionError):
    """Raised when an upstream API rate limits and retries are exhausted."""


class NormalizationError(AssessmentError):
    """Raised when raw evidence cannot be normalized into the inventory model."""


class RuleError(AssessmentError):
    """Raised when a rule definition or rule execution is invalid."""


class ScoringError(AssessmentError):
    """Raised when a scorecard cannot be computed from rule outcomes."""


class PersistenceError(AssessmentError):
    """Raised when writing to the Lakehouse medallion layers fails."""


class ConfigurationError(AssessmentError):
    """Raised when the run configuration is missing or inconsistent."""


class ReviewError(AssessmentError):
    """Raised when the preceptorship loop cannot review a run."""


class DeploymentError(AssessmentError):
    """Raised when the Fabric solution cannot be deployed into our own workspace."""
