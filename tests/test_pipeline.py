"""Collection, persistence and end-to-end CLI behaviour."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace

from fabric_iq.collectors.base import BronzeRecord, CollectionResult, empty_inventory
from fabric_iq.collectors.offline import OfflineCollector
from fabric_iq.errors import CollectionError, NormalizationError, PersistenceError
from fabric_iq.lakehouse import LakehouseWriter, gold_mart_rows
from fabric_iq.models import ObjectType
from fabric_iq.remediation import build_backlog
from fabric_iq.reporting import to_console, to_html
from fabric_iq.scoring import assess
from tests.helpers import REPO_ROOT, SAMPLE_TENANT


class TestCollectionResult(unittest.TestCase):
    def test_empty_inventory_validates(self):
        CollectionResult(inventory=empty_inventory("t")).validate()

    def test_missing_section_is_rejected(self):
        inventory = empty_inventory("t")
        del inventory["reports"]
        with self.assertRaises(NormalizationError):
            CollectionResult(inventory=inventory).validate()

    def test_wrong_section_type_is_rejected(self):
        inventory = empty_inventory("t")
        inventory["reports"] = {"not": "a list"}
        with self.assertRaises(NormalizationError):
            CollectionResult(inventory=inventory).validate()

    def test_non_mapping_inventory_is_rejected(self):
        with self.assertRaises(NormalizationError):
            CollectionResult(inventory=[]).validate()

    def test_errors_are_carried_into_the_inventory(self):
        result = CollectionResult(inventory=empty_inventory("t"))
        result.errors.append({"endpoint": "scanner", "message": "429"})
        result.validate()
        self.assertEqual(len(result.inventory["collection_errors"]), 1)

    def test_bronze_hash_is_stable_and_content_sensitive(self):
        first = BronzeRecord(endpoint="/getInfo", payload={"a": 1})
        same = BronzeRecord(endpoint="/getInfo", payload={"a": 1})
        other = BronzeRecord(endpoint="/getInfo", payload={"a": 2})
        self.assertEqual(first.content_hash, same.content_hash)
        self.assertNotEqual(first.content_hash, other.content_hash)


class TestOfflineCollector(unittest.TestCase):
    def test_sample_tenant_collects_and_validates(self):
        result = OfflineCollector(SAMPLE_TENANT).collect().validate()
        self.assertTrue(result.inventory["semantic_models"])
        self.assertTrue(result.bronze, "offline collection must still leave an evidence trail")

    def test_missing_path_raises_a_domain_error(self):
        with self.assertRaises(CollectionError):
            OfflineCollector(os.path.join(REPO_ROOT, "does-not-exist")).collect()

    def test_malformed_json_raises_a_domain_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "tenant.json"), "w", encoding="utf-8") as handle:
                handle.write("{not json")
            with self.assertRaises(CollectionError):
                OfflineCollector(tmp).collect()

    def test_partial_directory_still_produces_a_valid_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "tenant.json"), "w", encoding="utf-8") as handle:
                json.dump({"id": "t", "name": "T"}, handle)
            result = OfflineCollector(tmp).collect().validate()
        self.assertEqual(result.inventory["reports"], [])


class TestLakehouseWriter(unittest.TestCase):
    def setUp(self):
        self.collection = OfflineCollector(SAMPLE_TENANT).collect().validate()
        self.run = assess(self.collection.inventory, run_id="run_lh")
        self.backlog = build_backlog(self.run)

    def test_root_and_run_id_are_required(self):
        with self.assertRaises(PersistenceError):
            LakehouseWriter(root="", run_id="r")
        with self.assertRaises(PersistenceError):
            LakehouseWriter(root="x", run_id="")

    def test_every_gold_mart_is_written_as_ndjson(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = LakehouseWriter(root=tmp, run_id="run_lh")
            written = writer.write_run(
                self.run, self.backlog,
                inventory=self.collection.inventory, bronze=self.collection.bronze,
            )
            for name, path in written["gold"].items():
                with self.subTest(mart=name):
                    self.assertTrue(os.path.exists(path))
                    with open(path, encoding="utf-8") as handle:
                        for line in handle:
                            if line.strip():
                                json.loads(line)

    def test_every_gold_row_carries_the_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = LakehouseWriter(root=tmp, run_id="run_lh")
            written = writer.write_gold(self.run, self.backlog)
            for name, path in written.items():
                with open(path, encoding="utf-8") as handle:
                    rows = [json.loads(line) for line in handle if line.strip()]
                for row in rows:
                    with self.subTest(mart=name):
                        self.assertEqual(row.get("run_id"), "run_lh")

    def test_run_summary_mart_has_one_ai_readable_run_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = LakehouseWriter(root=tmp, run_id="run_lh")
            written = writer.write_gold(self.run, self.backlog)
            with open(written["MartRunSummary"], encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["run_id"], "run_lh")
        self.assertEqual(row["tenant_id"], self.run.tenant_id)
        self.assertEqual(row["ruleset_version"], self.run.ruleset_version)
        leaf_count = sum(
            len(self.run.by_type(object_type))
            for object_type in (ObjectType.SEMANTIC_MODEL, ObjectType.REPORT, ObjectType.DATA_AGENT)
        )
        self.assertEqual(row["assessed_object_count"], leaf_count)
        self.assertEqual(row["blocking_findings_count"], len(self.run.blocking_findings))
        self.assertEqual(row["backlog_items_count"], len(self.backlog.items))

    def test_run_trend_mart_is_empty_without_a_baseline(self):
        marts = gold_mart_rows(self.run, self.backlog, run_id="run_lh")

        self.assertEqual(marts["MartRunTrend"], [])

    def test_run_trend_mart_classifies_regressions_with_a_baseline(self):
        baseline = replace(self.run, run_id="baseline")
        current_cards = list(self.run.scorecards)
        object_index = next(
            i for i, card in enumerate(current_cards)
            if card.object_type is ObjectType.SEMANTIC_MODEL
        )
        current_cards[object_index] = replace(
            current_cards[object_index],
            score=max(0, current_cards[object_index].score - 10),
        )
        current = replace(self.run, run_id="current", scorecards=current_cards)

        marts = gold_mart_rows(current, self.backlog, run_id="current", baseline_run=baseline)
        trend_rows = marts["MartRunTrend"]
        target_rows = [row for row in trend_rows if row["object_id"] == current_cards[object_index].object_id]

        self.assertEqual(len(target_rows), 1)
        self.assertEqual(target_rows[0]["classification"], "quality_regression")
        self.assertLess(target_rows[0]["score_delta"], 0)

    def test_reruns_are_idempotent_per_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = LakehouseWriter(root=tmp, run_id="run_lh")
            first = writer.write_gold(self.run, self.backlog)
            sizes = {p: os.path.getsize(p) for p in first.values()}
            second = writer.write_gold(self.run, self.backlog)
            self.assertEqual(set(first), set(second))
            self.assertEqual(sizes, {p: os.path.getsize(p) for p in second.values()})


class TestReporting(unittest.TestCase):
    def setUp(self):
        inventory = OfflineCollector(SAMPLE_TENANT).collect().validate().inventory
        self.run = assess(inventory, run_id="run_report")
        self.backlog = build_backlog(self.run)

    def test_console_report_names_blocking_objects(self):
        text = to_console(self.run, self.backlog)
        self.assertIn("run_report", text)
        for finding in self.run.blocking_findings[:3]:
            self.assertIn(finding.object_name, text)

    def test_html_report_escapes_markup(self):
        self.run.scorecards[0].object_name = "<script>alert(1)</script>"
        html = to_html(self.run, self.backlog)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "assess.py", *args],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )

    def test_version_exits_cleanly(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)

    def test_list_rules_reports_the_catalogue(self):
        result = self.run_cli("--list-rules")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SEM-001", result.stdout)

    def test_end_to_end_run_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli("--inventory", SAMPLE_TENANT, "--out", tmp, "--review", "--quiet")
            self.assertEqual(result.returncode, 0, result.stderr)
            produced = os.listdir(tmp)
            self.assertTrue(any(f.endswith("_assessment.json") for f in produced), produced)
            self.assertTrue(any(f.endswith("_review.json") for f in produced), produced)

    def test_fail_on_blocking_sets_a_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(
                "--inventory", SAMPLE_TENANT, "--out", tmp, "--quiet", "--fail-on-blocking"
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_unknown_inventory_fails_with_error_code(self):
        result = self.run_cli("--inventory", os.path.join(REPO_ROOT, "nope"), "--quiet")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
