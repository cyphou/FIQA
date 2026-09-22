"""Power BI (.pbip) report generator."""

import csv
import json
import os
import shutil
import tempfile
import unittest

from fabric_iq.lakehouse import GOLD_TABLES
from fabric_iq.powerbi import PowerBiReportWriter, build_definition_pbir_live, build_model_bim_directlake
from fabric_iq.remediation import build_backlog
from fabric_iq.scoring import assess
from tests.helpers import minimal_inventory, ready_model


def sample_run():
    inventory = minimal_inventory(
        workspaces=[{"id": "ws", "name": "WS", "parent_id": "tenant-test",
                     "capacity_sku": "F64", "is_pro": False}],
        semantic_models=[
            ready_model(id="sm-good", name="Good Model", parent_id="ws"),
            ready_model(id="sm-bad", name="Bad Model", parent_id="ws",
                        rls_required=True, rls_roles=[], ai_data_schema={"selected_objects": 0}),
        ],
    )
    return assess(inventory, run_id="run_powerbi_test")


class TestPowerBiReportWriter(unittest.TestCase):
    def setUp(self):
        self.run = sample_run()
        self.backlog = build_backlog(self.run)
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.root = os.path.join(self.tmpdir, "powerbi")
        PowerBiReportWriter(root=self.root).write_run(self.run, self.backlog)

    def _load_json(self, *parts):
        with open(os.path.join(self.root, *parts), encoding="utf-8") as handle:
            return json.load(handle)

    def _read_csv(self, name):
        with open(os.path.join(self.root, "data", f"{name}.csv"), encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_expected_files_exist(self):
        expected = [
            "IsFabricReadyForIQ.pbip",
            "FabricIQ_Theme.json",
            "README.md",
            os.path.join("IsFabricReadyForIQ.Report", "report.json"),
            os.path.join("IsFabricReadyForIQ.Report", "definition.pbir"),
            os.path.join("IsFabricReadyForIQ.SemanticModel", "model.bim"),
            os.path.join("IsFabricReadyForIQ.SemanticModel", "definition.pbism"),
        ]
        for table in GOLD_TABLES:
            expected.append(os.path.join("data", f"{table}.csv"))
        for rel in expected:
            with self.subTest(rel=rel):
                self.assertTrue(os.path.isfile(os.path.join(self.root, rel)), rel)

    def test_report_definition_pbir_points_at_semantic_model(self):
        # Required artifact: without it Power BI Desktop reports "Required
        # artifact is missing" for the report and refuses to load it.
        pbir = self._load_json("IsFabricReadyForIQ.Report", "definition.pbir")
        self.assertEqual(
            pbir["datasetReference"]["byPath"]["path"],
            "../IsFabricReadyForIQ.SemanticModel",
        )

    def test_build_definition_pbir_live_uses_by_connection(self):
        # Fabric REST API deployments must use byConnection, not byPath (no
        # folder tree exists server-side for a relative path to resolve
        # against) -- see fabric_iq.deployment for the API-driven caller.
        pbir = build_definition_pbir_live("11111111-2222-3333-4444-555555555555")
        self.assertEqual(
            pbir["datasetReference"]["byConnection"]["connectionString"],
            "semanticmodelid=11111111-2222-3333-4444-555555555555",
        )
        self.assertNotIn("byPath", pbir["datasetReference"])

    def test_build_definition_pbir_live_requires_semantic_model_id(self):
        with self.assertRaises(ValueError):
            build_definition_pbir_live("")

    def test_semantic_model_definition_pbism_declares_tmsl_version(self):
        # Required artifact: without it Power BI Desktop reports "Required
        # artifact is missing" for the dataset and refuses to load it.
        pbism = self._load_json("IsFabricReadyForIQ.SemanticModel", "definition.pbism")
        self.assertEqual(pbism["version"], "1.0")
        self.assertIn("$schema", pbism)

    def test_pbip_is_valid_json_and_points_at_report(self):
        doc = self._load_json("IsFabricReadyForIQ.pbip")
        self.assertEqual(doc["artifacts"][0]["report"]["path"], "IsFabricReadyForIQ.Report")

    def test_model_bim_has_the_gold_mart_tables(self):
        bim = self._load_json("IsFabricReadyForIQ.SemanticModel", "model.bim")
        tables = {t["name"]: t for t in bim["model"]["tables"]}
        self.assertEqual(set(tables), set(GOLD_TABLES))

        run_summary_columns = {c["name"] for c in tables["MartRunSummary"]["columns"]}
        self.assertIn("run_id", run_summary_columns)
        self.assertIn("assessed_object_count", run_summary_columns)
        self.assertIn("average_object_confidence", run_summary_columns)

        object_columns = {c["name"] for c in tables["MartObjectReadiness"]["columns"]}
        self.assertIn("object_id", object_columns)
        self.assertIn("score", object_columns)
        self.assertIn("eligible", object_columns)

        measure_names = {m["name"] for m in tables["MartObjectReadiness"]["measures"]}
        self.assertIn("Avg Score", measure_names)
        self.assertIn("Eligible %", measure_names)

        # Flat marts: DirectLake reads Delta tables directly, no relationships
        # are modeled between the standalone marts.
        self.assertEqual(bim["model"]["relationships"], [])

    def test_directlake_model_uses_lakehouse_physical_table_names(self):
        bim = build_model_bim_directlake(
            "example.datawarehouse.fabric.microsoft.com",
            "00000000-0000-0000-0000-000000000000",
        )
        tables = {t["name"]: t for t in bim["model"]["tables"]}
        self.assertEqual(set(tables), set(GOLD_TABLES))

        for table_name, table in tables.items():
            with self.subTest(table_name=table_name):
                source = table["partitions"][0]["source"]
                self.assertEqual(source["type"], "entity")
                self.assertEqual(source["schemaName"], "dbo")
                self.assertEqual(source["entityName"], table_name.lower())
                self.assertTrue(table.get("description"))
                self.assertTrue(all(column.get("description") for column in table["columns"]))

    def test_report_json_has_six_pages(self):
        report = self._load_json("IsFabricReadyForIQ.Report", "report.json")
        self.assertEqual(len(report["sections"]), 6)
        names = [s["displayName"] for s in report["sections"]]
        self.assertEqual(
            names,
            [
                "Overview",
                "Tenant & Workspaces",
                "Object Readiness",
                "Blocking Findings",
                "Remediation Backlog",
                "Coverage & Freshness",
            ],
        )
        # Overview page carries six KPI cards.
        self.assertEqual(len(report["sections"][0]["visualContainers"]), 6)
        # Tenant & Workspaces stacks two tables (tenant + workspace).
        self.assertEqual(len(report["sections"][1]["visualContainers"]), 2)
        # Every other data page carries exactly one tableEx visual.
        for section in report["sections"][2:]:
            self.assertEqual(len(section["visualContainers"]), 1)

    def test_visual_configs_are_valid_json(self):
        report = self._load_json("IsFabricReadyForIQ.Report", "report.json")
        for section in report["sections"]:
            for visual in section["visualContainers"]:
                config = json.loads(visual["config"])
                self.assertIn("singleVisual", config)

    def test_csv_row_counts_match_run(self):
        object_rows = self._read_csv("MartObjectReadiness")
        backlog_rows = self._read_csv("MartRemediationBacklog")

        self.assertEqual(len(object_rows), len(self.run.scorecards) - 2)  # tenant + workspace excluded
        self.assertEqual(len(backlog_rows), len(self.backlog.items))

    def test_object_csv_object_ids_match_run(self):
        object_rows = self._read_csv("MartObjectReadiness")
        object_ids = {row["object_id"] for row in object_rows}
        self.assertTrue(object_ids <= {c.object_id for c in self.run.scorecards})

    def test_backlog_csv_includes_object_id(self):
        rows = self._read_csv("MartRemediationBacklog")
        self.assertTrue(rows)
        expected_ids = {i.object_id for i in self.backlog.items}
        self.assertEqual({row["object_id"] for row in rows}, expected_ids)

    def test_theme_has_brand_palette(self):
        theme = self._load_json("FabricIQ_Theme.json")
        self.assertIn("#0f6d5c", theme["dataColors"])


if __name__ == "__main__":
    unittest.main()
