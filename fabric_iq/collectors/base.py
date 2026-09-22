"""Collector contract and the Bronze evidence envelope."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fabric_iq.errors import NormalizationError
from fabric_iq.models import utcnow

#: Inventory sections every collector must return.
INVENTORY_SECTIONS = (
    "tenant",
    "workspaces",
    "semantic_models",
    "reports",
    "data_agents",
)


@dataclass
class BronzeRecord:
    """Immutable proof of one upstream call, before any interpretation."""

    endpoint: str
    collected_at: str = field(default_factory=utcnow)
    status_code: int = 200
    duration_ms: int = 0
    correlation_id: str = ""
    identity: str = ""
    payload: Any = None
    schema_version: str = "1.0"

    @property
    def content_hash(self) -> str:
        blob = json.dumps(self.payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "collected_at": self.collected_at,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "correlation_id": self.correlation_id,
            "identity": self.identity,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
            "payload": self.payload,
        }


@dataclass
class CollectionResult:
    """Normalized inventory plus the Bronze evidence that produced it."""

    inventory: dict[str, Any]
    bronze: list[BronzeRecord] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "offline"

    def validate(self) -> "CollectionResult":
        """Fail fast on a malformed inventory rather than scoring garbage."""
        if not isinstance(self.inventory, dict):
            raise NormalizationError("inventory must be a mapping")
        missing = [s for s in INVENTORY_SECTIONS if s not in self.inventory]
        if missing:
            raise NormalizationError(f"inventory missing sections: {', '.join(missing)}")
        if not isinstance(self.inventory.get("tenant"), dict):
            raise NormalizationError("inventory.tenant must be a mapping")
        for section in INVENTORY_SECTIONS[1:]:
            if not isinstance(self.inventory[section], list):
                raise NormalizationError(f"inventory.{section} must be a list")
        self.inventory.setdefault("collection_errors", []).extend(self.errors)
        return self


class Collector(ABC):
    """Read-only evidence source."""

    mode = "abstract"

    @abstractmethod
    def collect(self) -> CollectionResult:
        """Return the normalized inventory and its Bronze evidence."""

    def record_error(
        self,
        result: CollectionResult,
        endpoint: str,
        message: str,
        *,
        recoverable: bool = True,
    ) -> None:
        """Log a collection failure without aborting the whole run.

        A missing section must surface as reduced coverage, never as a silent
        pass, so the error is carried all the way into the scorecards.
        """
        result.errors.append(
            {
                "endpoint": endpoint,
                "message": message,
                "recoverable": recoverable,
                "occurred_at": utcnow(),
            }
        )


def empty_inventory(tenant_id: str = "") -> dict[str, Any]:
    """Return a structurally valid, empty inventory."""
    return {
        "tenant": {"id": tenant_id, "name": tenant_id},
        "workspaces": [],
        "semantic_models": [],
        "reports": [],
        "data_agents": [],
        "collection_errors": [],
    }
