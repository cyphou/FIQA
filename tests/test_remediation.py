"""Remediation backlog construction and prioritisation."""

import csv
import json
import os
import tempfile
import unittest

from fabric_iq.models import Effort, ObjectType, Severity
from fabric_iq.remediation import EFFORT_DAYS, build_backlog
from fabric_iq.scoring import assess
from tests.helpers import minimal_inventory, ready_model


def broken_run():
    inventory = minimal_inventory(
        workspaces=[{"id": "ws", "name": "WS", "parent_id": "tenant-test",
                     "capacity_sku": "F64", "is_pro": False}],
        semantic_models=[
            ready_model(id="sm-bad", name="Bad Model", parent_id="ws",
                        rls_required=True, rls_roles=[], ai_data_schema={"selected_objects": 0}),
            ready_model(id="sm-good", name="Good Model", parent_id="ws"),
        ],
    )
    return assess(inventory, run_id="run_backlog")


class TestBacklog(unittest.TestCase):
    def setUp(self):
        self.run = broken_run()
        self.backlog = build_backlog(self.run)

    def test_healthy_object_produces_no_item(self):
        self.assertNotIn("sm-good", {i.object_id for i in self.backlog.items})

    def test_every_item_is_actionable(self):
        for item in self.backlog.items:
            with self.subTest(rule=item.rule_id):
                self.assertTrue(item.action.strip())
                self.assertTrue(item.owner_role.strip())
                self.assertTrue(item.object_name.strip())

    def test_blocking_items_come_first(self):
        priorities = [i.priority for i in self.backlog.items]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        top_severities = {i.severity for i in self.backlog.items[:1]}
        self.assertIn(Severity.BLOCKING.value, {s.value if hasattr(s, "value") else s for s in top_severities})

    def test_blocking_items_are_isolated(self):
        for item in self.backlog.blocking_items:
            self.assertEqual(
                item.severity.value if hasattr(item.severity, "value") else item.severity,
                Severity.BLOCKING.value,
            )

    def test_effort_is_translated_into_days(self):
        self.assertGreater(self.backlog.total_days, 0.0)
        for item in self.backlog.items:
            with self.subTest(rule=item.rule_id):
                self.assertEqual(item.estimated_days, EFFORT_DAYS[item.effort])

    def test_grouping_by_owner_keeps_every_item(self):
        grouped = self.backlog.by_owner()
        self.assertEqual(sum(len(v) for v in grouped.values()), len(self.backlog.items))

    def test_top_is_bounded(self):
        self.assertLessEqual(len(self.backlog.top(3)), 3)

    def test_excluding_partials_shrinks_the_backlog(self):
        full = build_backlog(self.run, include_partial=True)
        failures_only = build_backlog(self.run, include_partial=False)
        self.assertLessEqual(len(failures_only.items), len(full.items))

    def test_empty_run_yields_an_empty_backlog(self):
        clean = assess(minimal_inventory(semantic_models=[ready_model()]), run_id="run_clean")
        backlog = build_backlog(clean, include_partial=False)
        self.assertEqual(backlog.blocking_items, [])

    def test_json_export_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "backlog.json")
            self.backlog.to_json(path)
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        self.assertEqual(len(payload["items"]), len(self.backlog.items))

    def test_csv_export_has_one_row_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "backlog.csv")
            self.backlog.to_csv(path)
            with open(path, encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(self.backlog.items))


if __name__ == "__main__":
    unittest.main()
