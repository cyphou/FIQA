"""Offline collector: read a normalized inventory from JSON on disk.

This is the default mode. It lets the whole rule set, scoring engine and
preceptorship loop be developed and tested without touching a real tenant, and
it makes every assessment reproducible from its Bronze evidence.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fabric_iq.collectors.base import (
    BronzeRecord,
    CollectionResult,
    Collector,
    INVENTORY_SECTIONS,
    empty_inventory,
)
from fabric_iq.errors import CollectionError

#: File name expected for each inventory section inside a fixture directory.
SECTION_FILES = {section: f"{section}.json" for section in INVENTORY_SECTIONS}


class OfflineCollector(Collector):
    """Load an inventory either from a single JSON file or a fixture directory."""

    mode = "offline"

    def __init__(self, path: str) -> None:
        self.path = path

    def collect(self) -> CollectionResult:
        if not os.path.exists(self.path):
            raise CollectionError(f"inventory path not found: {self.path}")
        if os.path.isdir(self.path):
            result = self._collect_directory()
        else:
            result = self._collect_file()
        return result.validate()

    # ── loaders ───────────────────────────────────────────────────

    def _collect_file(self) -> CollectionResult:
        payload = self._read_json(self.path)
        if not isinstance(payload, dict):
            raise CollectionError(f"{self.path} must contain a JSON object")
        inventory = empty_inventory()
        inventory.update(payload)
        return CollectionResult(
            inventory=inventory,
            bronze=[BronzeRecord(endpoint=f"file://{self.path}", identity="offline", payload=payload)],
            mode=self.mode,
        )

    def _collect_directory(self) -> CollectionResult:
        inventory = empty_inventory()
        result = CollectionResult(inventory=inventory, mode=self.mode)

        for section, filename in SECTION_FILES.items():
            full_path = os.path.join(self.path, filename)
            if not os.path.exists(full_path):
                self.record_error(
                    result,
                    f"file://{full_path}",
                    f"missing fixture for section '{section}'",
                )
                continue
            payload = self._read_json(full_path)
            inventory[section] = payload
            result.bronze.append(
                BronzeRecord(endpoint=f"file://{full_path}", identity="offline", payload=payload)
            )

        return result

    @staticmethod
    def _read_json(path: str) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise CollectionError(f"cannot read {path}: {exc}") from exc
