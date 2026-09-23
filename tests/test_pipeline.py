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
from fabric_iq.lakehouse import LakehouseWriter, gold_mart_rows, select_latest_baseline_run
from fabric_iq.models import Effort, ObjectType, ReadinessStatus
from fabric_iq.remediation import build_backlog
from fabric_iq.reporting import (
    INTERPRETATION_GUIDE,
    ORIENTATION_HTML_TITLE,
    ORIENTATION_TITLE,
    to_console,
    to_html,
)
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

    def _run_without_backlog_item(self, run, item):
        cards = []
        for card in run.scorecards:
            findings = [
                finding for finding in card.findings
                if not (finding.rule_id == item.rule_id and finding.object_id == item.object_id)
            ]
            cards.append(replace(card, findings=findings))
        return replace(run, scorecards=cards)

    def _run_with_changed_effort(self, run, item):
        replacement_effort = Effort.XL if item.effort is not Effort.XL else Effort.XS
        cards = []
        for card in run.scorecards:
            findings = []
            for finding in card.findings:
                if finding.rule_id == item.rule_id and finding.object_id == item.object_id:
                    findings.append(replace(finding, effort=replacement_effort))
                else:
                    findings.append(finding)
            cards.append(replace(card, findings=findings))
        return replace(run, scorecards=cards)

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

    def test_remediation_burndown_marks_first_run_items_as_new(self):
        marts = gold_mart_rows(self.run, self.backlog, run_id="run_lh")
        rows = marts["MartRemediationBurnDown"]

        self.assertEqual(len(rows), len(self.backlog.items))
        self.assertEqual({row["lifecycle_status"] for row in rows}, {"new"})
        self.assertTrue(all(row["baseline_run_id"] == "" for row in rows))

    def test_remediation_burndown_marks_resolved_items(self):
        item = self.backlog.items[0]
        current = replace(
            self._run_without_backlog_item(self.run, item),
            run_id="current",
        )
        current_backlog = build_backlog(current)

        marts = gold_mart_rows(
            current,
            current_backlog,
            run_id="current",
            history_runs=[replace(self.run, run_id="baseline")],
        )
        target = [
            row for row in marts["MartRemediationBurnDown"]
            if row["rule_id"] == item.rule_id and row["object_id"] == item.object_id
        ]

        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["lifecycle_status"], "resolved")
        self.assertLess(target[0]["estimated_days_delta"], 0)

    def test_remediation_burndown_marks_reopened_items(self):
        item = self.backlog.items[0]
        older = replace(self.run, run_id="older")
        baseline = replace(
            self._run_without_backlog_item(self.run, item),
            run_id="baseline",
        )
        current = replace(self.run, run_id="current")

        marts = gold_mart_rows(
            current,
            build_backlog(current),
            run_id="current",
            history_runs=[older, baseline],
        )
        target = [
            row for row in marts["MartRemediationBurnDown"]
            if row["rule_id"] == item.rule_id and row["object_id"] == item.object_id
        ]

        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["lifecycle_status"], "reopened")
        self.assertEqual(target[0]["previous_seen_run_id"], "older")

    def test_remediation_burndown_marks_priority_changes(self):
        item = self.backlog.items[0]
        current = replace(
            self._run_with_changed_effort(self.run, item),
            run_id="current",
        )

        marts = gold_mart_rows(
            current,
            build_backlog(current),
            run_id="current",
            history_runs=[replace(self.run, run_id="baseline")],
        )
        target = [
            row for row in marts["MartRemediationBurnDown"]
            if row["rule_id"] == item.rule_id and row["object_id"] == item.object_id
        ]

        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["lifecycle_status"], "changed_priority")
        self.assertNotEqual(target[0]["priority_delta"], 0)

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

    def test_assessment_run_json_can_be_reloaded_for_trend_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "baseline_assessment.json")
            self.run.to_json(path)

            loaded = type(self.run).from_json(path)

        self.assertEqual(loaded.run_id, self.run.run_id)
        self.assertEqual(loaded.tenant_id, self.run.tenant_id)
        self.assertEqual(len(loaded.scorecards), len(self.run.scorecards))
        self.assertEqual(loaded.scorecards[0].object_type, self.run.scorecards[0].object_type)
        self.assertEqual(loaded.scorecards[0].status, self.run.scorecards[0].status)

    def test_latest_baseline_selector_picks_previous_same_ruleset_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            older = replace(
                self.run,
                run_id="run_older",
                started_at="2026-09-20T00:00:00+00:00",
                completed_at="2026-09-20T00:05:00+00:00",
            )
            latest = replace(
                self.run,
                run_id="run_latest",
                started_at="2026-09-21T00:00:00+00:00",
                completed_at="2026-09-21T00:05:00+00:00",
            )
            current = replace(
                self.run,
                run_id="run_current",
                started_at="2026-09-22T00:00:00+00:00",
                completed_at="2026-09-22T00:05:00+00:00",
            )
            older.to_json(os.path.join(tmp, "run_older_assessment.json"))
            latest.to_json(os.path.join(tmp, "run_latest_assessment.json"))
            current.to_json(os.path.join(tmp, "run_current_assessment.json"))

            baseline = select_latest_baseline_run(tmp, current)

        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.run_id, "run_latest")

    def test_latest_baseline_selector_ignores_different_ruleset_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_ruleset = replace(
                self.run,
                run_id="run_old_ruleset",
                ruleset_version="1900.01.1",
                started_at="2026-09-21T00:00:00+00:00",
                completed_at="2026-09-21T00:05:00+00:00",
            )
            current = replace(self.run, run_id="run_current")
            old_ruleset.to_json(os.path.join(tmp, "run_old_ruleset_assessment.json"))

            baseline = select_latest_baseline_run(tmp, current)

        self.assertIsNone(baseline)

    def test_writer_uses_selected_baseline_for_trend_mart(self):
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

        with tempfile.TemporaryDirectory() as tmp:
            writer = LakehouseWriter(root=tmp, run_id="current")
            written = writer.write_gold(current, self.backlog, baseline_run=baseline)
            with open(written["MartRunTrend"], encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]

        self.assertTrue(rows)
        self.assertEqual(rows[0]["baseline_run_id"], "baseline")
        self.assertEqual(rows[0]["current_run_id"], "current")

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


class TestReportOrientation(unittest.TestCase):
    """The CLI must orient a first-time operator without any external context.

    The Skill and the agent instructions are not available to a human running
    `assess.py`; these assertions are what keeps the standalone output honest.
    """

    def setUp(self):
        inventory = OfflineCollector(SAMPLE_TENANT).collect().validate().inventory
        self.run = assess(inventory, run_id="run_orient")
        self.backlog = build_backlog(self.run)
        self.not_evaluated = sum(
            1 for c in self.run.scorecards
            if c.status is ReadinessStatus.NOT_EVALUATED
        )

    def test_console_orientation_states_the_reading_order(self):
        text = to_console(self.run, self.backlog)
        self.assertIn(ORIENTATION_TITLE, text)
        self.assertIn(f"Blocking findings ({len(self.run.blocking_findings)})", text)
        self.assertIn("walls, not quality issues", text)
        self.assertIn(f"NOT EVALUATED ({self.not_evaluated})", text)
        self.assertIn("never by re-scoring", text)
        self.assertIn("coverage and confidence", text)
        self.assertIn(INTERPRETATION_GUIDE, text)

    def test_console_orientation_precedes_the_numbers_it_explains(self):
        text = to_console(self.run, self.backlog)
        self.assertLess(text.index(ORIENTATION_TITLE), text.index("TENANT ("))
        self.assertLess(
            text.index(ORIENTATION_TITLE), text.index("BLOCKING FINDINGS (")
        )

    def test_console_orientation_stays_short(self):
        text = to_console(self.run, self.backlog)
        block = text.split(ORIENTATION_TITLE, 1)[1].split("TENANT (", 1)[0]
        self.assertLessEqual(
            len([line for line in block.splitlines() if line.strip()]), 10,
            "orientation is turning into a manual; it must stay a few lines",
        )

    def test_console_orientation_does_not_move_a_single_value(self):
        with_orientation = to_console(self.run, self.backlog)
        block = with_orientation.split(ORIENTATION_TITLE, 1)[1].split("TENANT (", 1)[0]
        body = with_orientation.replace(block, "")
        for card in self.run.scorecards:
            with self.subTest(object_name=card.object_name):
                self.assertIn(f"{card.coverage:>4.0%} {card.confidence:>5.0%}", body)
                if card.status is not ReadinessStatus.NOT_EVALUATED:
                    self.assertIn(f"{card.score:5.1f}", body)

    def test_html_orientation_leads_the_report_and_is_escaped(self):
        html_text = to_html(self.run, self.backlog)
        self.assertIn(ORIENTATION_HTML_TITLE, html_text)
        self.assertIn(INTERPRETATION_GUIDE, html_text)
        self.assertIn("walls, not quality issues", html_text)
        self.assertIn("never by re-scoring", html_text)
        self.assertLess(
            html_text.index('id="sec-orientation"'),
            html_text.index('id="sec-blocking"'),
        )
        self.assertIn(f"<code>{INTERPRETATION_GUIDE}</code>", html_text)

    def test_orientation_reports_a_clean_run_without_inventing_walls(self):
        clean = replace(self.run, scorecards=[
            card for card in self.run.scorecards if not card.blocking_findings
        ])
        text = to_console(clean, build_backlog(clean))
        self.assertIn("Blocking findings (0)", text)
        self.assertIn("no object is structurally excluded", text)


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
