"""Deployment packaging must be provably correct before it ever hits a workspace."""

import base64
import json
import os
import unittest

from fabric_iq.deployment import (
    DEFAULT_SPARK_RUNTIME_VERSION,
    NOTEBOOK_ITEM,
    NOTEBOOK_SOURCE,
    PIPELINE_ITEM,
    PIPELINE_SOURCE,
    REPORT_ITEM,
    SEMANTIC_MODEL_ITEM,
    DeploymentConfig,
    build_notebook_content,
    build_pipeline_content,
    build_report_parts,
    build_semantic_model_parts,
    ensure_workspace_spark_runtime,
    get_lakehouse_sql_endpoint,
    inline_part,
    library_files,
    read_item_file,
    upload_library,
)
from fabric_iq.errors import ConfigurationError, DeploymentError

ITEMS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fabric", "items"
)
PACKAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fabric_iq"
)


class InlinePartTests(unittest.TestCase):
    def test_payload_round_trips_through_base64(self):
        part = inline_part("notebook-content.py", "# Fabric notebook source\n")
        self.assertEqual(part["payloadType"], "InlineBase64")
        self.assertEqual(
            base64.b64decode(part["payload"]).decode("utf-8"), "# Fabric notebook source\n"
        )

    def test_non_ascii_survives(self):
        part = inline_part("x.py", 'note = "préparé"\n')
        self.assertIn("préparé", base64.b64decode(part["payload"]).decode("utf-8"))


class NotebookBindingTests(unittest.TestCase):
    def setUp(self):
        self.source = read_item_file(ITEMS_ROOT, NOTEBOOK_ITEM, NOTEBOOK_SOURCE)

    def _meta(self, content):
        lines = content.splitlines()
        start = lines.index("# METADATA ********************") + 1
        while not lines[start].strip():
            start += 1
        block = []
        while lines[start].startswith("# META"):
            block.append(lines[start][len("# META") :].lstrip(" "))
            start += 1
        return json.loads("\n".join(block))

    def test_shipped_notebook_has_no_lakehouse_binding(self):
        self.assertEqual(self._meta(self.source)["dependencies"]["lakehouse"], {})

    def test_binding_injects_all_three_lakehouse_keys(self):
        content = build_notebook_content(
            self.source,
            workspace_id="ws-1",
            lakehouse_id="lh-1",
            lakehouse_name="FabricIQReadiness",
        )
        lakehouse = self._meta(content)["dependencies"]["lakehouse"]
        self.assertEqual(lakehouse["default_lakehouse"], "lh-1")
        self.assertEqual(lakehouse["default_lakehouse_name"], "FabricIQReadiness")
        self.assertEqual(lakehouse["default_lakehouse_workspace_id"], "ws-1")

    def test_binding_preserves_the_kernel_and_the_body(self):
        content = build_notebook_content(
            self.source, workspace_id="ws-1", lakehouse_id="lh-1", lakehouse_name="LH"
        )
        self.assertEqual(self._meta(content)["kernel_info"]["name"], "synapse_pyspark")
        self.assertTrue(content.startswith("# Fabric notebook source"))
        self.assertIn("# PARAMETERS CELL ********************", content)
        self.assertIn("notebookutils.notebook.exit", content)

    def test_default_tenant_is_injected_once(self):
        content = build_notebook_content(
            self.source,
            workspace_id="ws-1",
            lakehouse_id="lh-1",
            lakehouse_name="LH",
            default_tenant_id="tenant-9",
        )
        self.assertIn('tenant_id = "tenant-9"', content)
        self.assertNotIn('tenant_id = ""', content)

    def test_empty_tenant_leaves_the_parameter_blank(self):
        content = build_notebook_content(
            self.source, workspace_id="ws-1", lakehouse_id="lh-1", lakehouse_name="LH"
        )
        self.assertIn('tenant_id = ""', content)

    def test_notebook_publishes_delta_snapshot_by_default(self):
        self.assertIn('delta_publish_mode = "overwrite"', self.source)
        self.assertIn("delta_publish_mode must be 'overwrite' or 'append'", self.source)
        self.assertIn(".mode(delta_publish_mode)", self.source)

    def test_source_without_metadata_block_is_rejected(self):
        with self.assertRaises(DeploymentError):
            build_notebook_content(
                "# Fabric notebook source\n", workspace_id="w", lakehouse_id="l", lakehouse_name="n"
            )

    def test_unparsable_metadata_is_rejected(self):
        broken = "# Fabric notebook source\n\n# METADATA ********************\n\n# META {oops\n"
        with self.assertRaises(DeploymentError):
            build_notebook_content(
                broken, workspace_id="w", lakehouse_id="l", lakehouse_name="n"
            )


class PipelineBindingTests(unittest.TestCase):
    def setUp(self):
        self.source = read_item_file(ITEMS_ROOT, PIPELINE_ITEM, PIPELINE_SOURCE)

    def test_notebook_activity_is_bound_to_the_created_notebook(self):
        content = json.loads(
            build_pipeline_content(self.source, workspace_id="ws-1", notebook_id="nb-1")
        )
        activity = content["properties"]["activities"][0]
        self.assertEqual(activity["type"], "TridentNotebook")
        self.assertEqual(activity["typeProperties"]["notebookId"], "nb-1")
        self.assertEqual(activity["typeProperties"]["workspaceId"], "ws-1")

    def test_pipeline_forwards_the_tenant_parameter(self):
        content = json.loads(
            build_pipeline_content(
                self.source, workspace_id="ws-1", notebook_id="nb-1", default_tenant_id="tenant-9"
            )
        )
        self.assertEqual(
            content["properties"]["parameters"]["tenant_id"]["defaultValue"], "tenant-9"
        )
        forwarded = content["properties"]["activities"][0]["typeProperties"]["parameters"]
        self.assertIn("tenant_id", forwarded)

    def test_pipeline_without_notebook_activity_is_rejected(self):
        with self.assertRaises(DeploymentError):
            build_pipeline_content(
                json.dumps({"properties": {"activities": []}}),
                workspace_id="ws-1",
                notebook_id="nb-1",
            )

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(DeploymentError):
            build_pipeline_content("{oops", workspace_id="ws-1", notebook_id="nb-1")


class LibraryFileTests(unittest.TestCase):
    def test_every_module_is_collected_under_the_package_name(self):
        files = library_files(PACKAGE_ROOT)
        paths = {path for path, _ in files}
        self.assertIn("fabric_iq/scoring.py", paths)
        self.assertIn("fabric_iq/rules/data_agent_rules.py", paths)
        self.assertIn("fabric_iq/collectors/fabric_api.py", paths)
        self.assertTrue(all(path.startswith("fabric_iq/") for path in paths))

    def test_caches_and_non_python_files_are_excluded(self):
        paths = {path for path, _ in library_files(PACKAGE_ROOT)}
        self.assertFalse([p for p in paths if "__pycache__" in p])
        self.assertTrue(all(p.endswith(".py") for p in paths))

    def test_missing_package_is_rejected(self):
        with self.assertRaises(DeploymentError):
            library_files(os.path.join(PACKAGE_ROOT, "does-not-exist"))


class _RecordingClient:
    """Fake FabricRestClient that only records the paths it was asked to hit."""

    def __init__(self):
        self.requests: list[tuple[str, str]] = []

    def request(self, method, url, body=None):
        self.requests.append((method, url))
        return {}


class _SequencedClient:
    """Fake FabricRestClient that returns one canned payload per call, repeating the last."""

    def __init__(self, payloads):
        self._payloads = payloads
        self.calls = 0
        self.requests: list[tuple[str, str, object]] = []

    def request(self, method, path, body=None, *, headers=None):
        self.calls += 1
        self.requests.append((method, path, body))
        payload = self._payloads[min(self.calls - 1, len(self._payloads) - 1)]
        return 200, {}, payload


class UploadLibraryTests(unittest.TestCase):
    """OneLake DFS paths must use the Lakehouse item GUID, never its display name.

    Regression test for a bug where the display name was used as the OneLake path
    segment instead of the item id: OneLake requires the id unless the tenant has
    friendly-name support enabled (off by default), so a display-name path silently
    resolves to the wrong (or a nonexistent) location.
    """

    def test_paths_use_the_lakehouse_item_id_not_its_display_name(self):
        client = _RecordingClient()
        written = upload_library(
            client,
            workspace_id="ws-1",
            lakehouse_id="6a9e1b02-6c42-4644-9d25-06826d34a43e",
            files=[("fabric_iq/scoring.py", b"print('x')")],
        )

        self.assertEqual(
            written, ["ws-1/6a9e1b02-6c42-4644-9d25-06826d34a43e/Files/lib/fabric_iq/scoring.py"]
        )
        for _, url in client.requests:
            self.assertIn("6a9e1b02-6c42-4644-9d25-06826d34a43e", url)
            self.assertNotIn("FabricIQReadiness", url)

    def test_dfs_create_append_flush_sequence_is_issued_for_each_file(self):
        client = _RecordingClient()
        upload_library(
            client,
            workspace_id="ws-1",
            lakehouse_id="lh-1",
            files=[("fabric_iq/a.py", b"a"), ("fabric_iq/b.py", b"")],
        )

        actions = [u.split("?", 1)[1] for _, u in client.requests if "a.py" in u]
        self.assertEqual(actions, ["resource=file", "action=append&position=0", "action=flush&position=1"])

        # The empty file must still go through create + flush, but skip the append call.
        actions_empty = [u.split("?", 1)[1] for _, u in client.requests if "b.py" in u]
        self.assertEqual(actions_empty, ["resource=file", "action=flush&position=0"])


class DeploymentConfigTests(unittest.TestCase):
    def test_workspace_id_is_required(self):
        with self.assertRaises(ConfigurationError):
            DeploymentConfig(workspace_id="").validate()

    def test_defaults_point_at_the_shipped_items(self):
        config = DeploymentConfig(workspace_id="ws-1").validate()
        self.assertTrue(os.path.isdir(os.path.join(config.items_root, NOTEBOOK_ITEM)))
        self.assertTrue(os.path.isfile(os.path.join(config.package_root, "scoring.py")))
        self.assertTrue(os.path.isdir(os.path.join(config.items_root, SEMANTIC_MODEL_ITEM)))
        self.assertTrue(os.path.isdir(os.path.join(config.items_root, REPORT_ITEM)))
        self.assertEqual(config.directlake_schema, "dbo")

    def test_empty_display_name_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            DeploymentConfig(workspace_id="ws-1", lakehouse_name="").validate()

    def test_empty_semantic_model_or_report_name_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            DeploymentConfig(workspace_id="ws-1", semantic_model_name="").validate()
        with self.assertRaises(ConfigurationError):
            DeploymentConfig(workspace_id="ws-1", report_name="").validate()


class LakehouseSqlEndpointTests(unittest.TestCase):
    """DirectLake needs the Lakehouse's SQL analytics endpoint, which provisions asynchronously."""

    def test_polls_until_the_endpoint_is_ready(self):
        provisioning = {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}}
        ready = {
            "properties": {
                "sqlEndpointProperties": {
                    "provisioningStatus": "Success",
                    "connectionString": "srv.datawarehouse.fabric.microsoft.com",
                    "id": "endpoint-guid",
                }
            }
        }
        client = _SequencedClient([provisioning, ready])
        sleeps = []

        connection_string, endpoint_id = get_lakehouse_sql_endpoint(
            client, "ws-1", "lh-1", poll_seconds=0.01, sleep=sleeps.append
        )

        self.assertEqual(connection_string, "srv.datawarehouse.fabric.microsoft.com")
        self.assertEqual(endpoint_id, "endpoint-guid")
        self.assertEqual(sleeps, [0.01])

    def test_failed_provisioning_raises(self):
        failed = {"properties": {"sqlEndpointProperties": {"provisioningStatus": "Failed"}}}
        client = _SequencedClient([failed])
        with self.assertRaises(DeploymentError):
            get_lakehouse_sql_endpoint(client, "ws-1", "lh-1", poll_seconds=0.01, sleep=lambda _: None)

    def test_timeout_raises(self):
        stuck = {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}}
        client = _SequencedClient([stuck])
        with self.assertRaises(DeploymentError):
            get_lakehouse_sql_endpoint(
                client, "ws-1", "lh-1", max_seconds=0, poll_seconds=0.01, sleep=lambda _: None
            )


class WorkspaceSparkRuntimeTests(unittest.TestCase):
    """Deploying should upgrade a stale workspace Spark runtime, and only when needed."""

    def test_default_config_targets_the_newest_runtime(self):
        self.assertEqual(DeploymentConfig(workspace_id="ws-1").spark_runtime_version, DEFAULT_SPARK_RUNTIME_VERSION)

    def test_patches_when_the_current_runtime_is_older(self):
        client = _SequencedClient([{"environment": {"runtimeVersion": "1.3"}}])
        result = ensure_workspace_spark_runtime(client, "ws-1", "2.0")

        self.assertEqual(result, {"changed": True, "runtime_version": "2.0", "previous_version": "1.3", "skipped": False})
        methods = [method for method, _, _ in client.requests]
        self.assertEqual(methods, ["GET", "PATCH"])
        patch_method, patch_path, patch_body = client.requests[1]
        self.assertEqual(patch_path, "workspaces/ws-1/spark/settings")
        self.assertEqual(patch_body, {"environment": {"runtimeVersion": "2.0"}})

    def test_no_patch_when_already_on_the_target_runtime(self):
        client = _SequencedClient([{"environment": {"runtimeVersion": "2.0"}}])
        result = ensure_workspace_spark_runtime(client, "ws-1", "2.0")

        self.assertEqual(result, {"changed": False, "runtime_version": "2.0", "skipped": False})
        self.assertEqual([method for method, _, _ in client.requests], ["GET"])

    def test_empty_version_skips_without_any_request(self):
        client = _SequencedClient([{}])
        result = ensure_workspace_spark_runtime(client, "ws-1", "")

        self.assertEqual(result, {"changed": False, "runtime_version": None, "skipped": True})
        self.assertEqual(client.requests, [])


class SemanticModelPartsTests(unittest.TestCase):
    def test_parts_have_model_bim_pbism_and_platform(self):
        parts = build_semantic_model_parts(
            ITEMS_ROOT,
            sql_endpoint_connection_string="srv.datawarehouse.fabric.microsoft.com",
            sql_endpoint_id="endpoint-guid",
        )
        paths = {p["path"] for p in parts}
        self.assertEqual(paths, {"model.bim", "definition.pbism", ".platform"})
        for part in parts:
            self.assertEqual(part["payloadType"], "InlineBase64")

    def test_model_bim_partitions_use_directlake_not_an_import_m_query(self):
        parts = build_semantic_model_parts(
            ITEMS_ROOT,
            sql_endpoint_connection_string="srv.datawarehouse.fabric.microsoft.com",
            sql_endpoint_id="endpoint-guid",
        )
        model_bim = json.loads(
            base64.b64decode(next(p["payload"] for p in parts if p["path"] == "model.bim"))
        )
        partitions = [
            partition
            for table in model_bim["model"]["tables"]
            for partition in table["partitions"]
        ]
        self.assertTrue(partitions)
        for partition in partitions:
            self.assertEqual(partition["mode"], "directLake")
            self.assertEqual(partition["source"]["type"], "entity")
            self.assertEqual(partition["source"]["entityName"], partition["source"]["entityName"].lower())
        self.assertNotIn("AzureStorage.DataLake", json.dumps(model_bim))
        self.assertIn("endpoint-guid", json.dumps(model_bim))
        for table in model_bim["model"]["tables"]:
            self.assertTrue(table.get("description"))
            self.assertTrue(all(column.get("description") for column in table["columns"]))


class ReportPartsTests(unittest.TestCase):
    def test_parts_have_report_json_pbir_and_platform(self):
        parts = build_report_parts(ITEMS_ROOT, semantic_model_id="sm-123")
        paths = {p["path"] for p in parts}
        self.assertEqual(paths, {"report.json", "definition.pbir", ".platform"})

    def test_report_config_json_is_never_included(self):
        parts = build_report_parts(ITEMS_ROOT, semantic_model_id="sm-123")
        self.assertNotIn("report.config.json", {p["path"] for p in parts})

    def test_pbir_uses_by_connection_with_the_given_semantic_model_id(self):
        parts = build_report_parts(ITEMS_ROOT, semantic_model_id="sm-123")
        pbir = json.loads(
            base64.b64decode(next(p["payload"] for p in parts if p["path"] == "definition.pbir"))
        )
        self.assertNotIn("byPath", pbir["datasetReference"])
        self.assertEqual(
            pbir["datasetReference"]["byConnection"]["connectionString"], "semanticmodelid=sm-123"
        )


if __name__ == "__main__":
    unittest.main()
