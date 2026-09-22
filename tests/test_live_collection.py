"""Synthetic tests for the read-only live collection foundation."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fabric_iq.collectors.fabric_api import (
    MAX_WORKSPACES_PER_SCAN,
    FabricApiCollector,
    FabricApiConfig,
    FabricHttpTransport,
    HttpResponse,
)
from fabric_iq.errors import CollectionError, ThrottlingError


class TestFabricHttpTransport(unittest.TestCase):
    def test_injects_bearer_token_and_retries_retry_after(self):
        state = {"calls": 0, "authorization": ""}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                state["calls"] += 1
                state["authorization"] = self.headers.get("Authorization", "")
                if state["calls"] == 1:
                    self.send_response(429)
                    self.send_header("Retry-After", "2")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"value": []}')

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        sleeps = []
        try:
            transport = FabricHttpTransport(
                lambda: "synthetic-token", max_retries=2, sleep=sleeps.append
            )
            response = transport("GET", f"http://127.0.0.1:{server.server_port}/items")
        finally:
            server.shutdown()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["authorization"], "Bearer synthetic-token")
        self.assertEqual(state["calls"], 2)
        self.assertEqual(sleeps, [2.0])

    def test_rejects_writes_and_non_scanner_post(self):
        transport = FabricHttpTransport(lambda: "synthetic-token")
        with self.assertRaises(CollectionError):
            transport("DELETE", "https://example.test/items")
        with self.assertRaises(CollectionError):
            transport("POST", "https://example.test/workspaces", {})

    def test_allows_scanner_post_carrying_scan_options_in_the_query_string(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"id": "scan-1", "status": "NotStarted"}')

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        try:
            transport = FabricHttpTransport(lambda: "synthetic-token")
            url = (
                f"http://127.0.0.1:{server.server_port}/admin/workspaces/getInfo"
                "?lineage=True&datasetSchema=True"
            )
            response = transport("POST", url, {"workspaces": ["synthetic-workspace"]})
        finally:
            server.shutdown()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.payload["id"], "scan-1")
        self.assertIn("lineage=True", received["path"])


class TestFabricApiCollector(unittest.TestCase):
    def config(self, checkpoint_path=None):
        return FabricApiConfig(
            tenant_id="synthetic-tenant",
            scanner_base_url="https://scanner.test/admin",
            fabric_base_url="https://fabric.test/v1",
            checkpoint_path=checkpoint_path,
        )

    def test_async_scan_flow_with_real_payload_shape(self):
        calls = []

        def transport(method, url, body):
            calls.append((method, url, body))
            if url.endswith("/tenantsettings"):
                return HttpResponse(
                    {
                        "tenantSettings": [
                            {"settingName": "FabricGAWorkloads", "enabled": True},
                            {"settingName": "OntologyPreview", "enabled": True},
                            {"settingName": "EnableAOAI", "enabled": True},
                            {"settingName": "AllowServicePrincipalsUseReadAdminAPIs", "enabled": True},
                            {"settingName": "EimInformationProtectionEdit", "enabled": False},
                        ]
                    },
                    200,
                )
            if "/groups?" in url:
                self.assertIn("$top=", url)
                self.assertIn("$skip=0", url)
                return HttpResponse(
                    {"value": [{"id": "w1"}, {"id": "w2"}]}, 200, {"x-ms-request-id": "groups-one"}, 5
                )
            if url.endswith("/capacities"):
                return HttpResponse(
                    {"value": [{"id": "cap-1", "sku": "F8", "state": "Active", "region": "West Europe"}]},
                    200,
                )
            if "/workspaces/getInfo" in url:
                self.assertEqual(body, {"workspaces": ["w1", "w2"]})
                self.assertIn("datasetSchema=True", url)
                return HttpResponse({"id": "scan-1", "status": "NotStarted"}, 200)
            if url.endswith("/scanStatus/scan-1"):
                # First poll still running, second one succeeds.
                status = "Succeeded" if any("scanStatus" in call[1] for call in calls[:-1]) else "Running"
                return HttpResponse({"id": "scan-1", "status": status}, 200)
            if url.endswith("/scanResult/scan-1"):
                return HttpResponse(
                    {
                        "workspaces": [
                            {
                                "id": "w1",
                                "name": "Synthetic",
                                "capacityId": "cap-1",
                                "isOnDedicatedCapacity": True,
                                "datasets": [
                                    {
                                        "id": "d1",
                                        "name": "Model",
                                        "isEffectiveIdentityRequired": False,
                                        "tables": [
                                            {
                                                "name": "factSales",
                                                "isHidden": False,
                                                "storageMode": "DirectLake",
                                                "columns": [
                                                    {
                                                        "name": "Amount",
                                                        "dataType": "Decimal",
                                                        "isHidden": False,
                                                        "columnType": "Data",
                                                    }
                                                ],
                                                "measures": [
                                                    {
                                                        "name": "Total Sales",
                                                        "expression": "SUM(factSales[Amount])",
                                                        "isHidden": False,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                                "reports": [{"id": "r1", "name": "Report", "datasetId": "d1"}],
                                # The Scanner returns a lone Fabric item as an object.
                                "DataAgent": {"id": "a1", "name": "Agent"},
                            }
                        ]
                    },
                    200,
                    {"x-ms-request-id": "scan-one"},
                )
            self.fail(f"unexpected request: {method} {url}")

        result = FabricApiCollector(self.config(), transport, sleep=lambda _: None).collect()

        self.assertEqual(len(result.inventory["workspaces"]), 1)
        workspace = result.inventory["workspaces"][0]
        self.assertEqual(workspace["capacity_sku"], "F8")
        self.assertEqual(workspace["capacity_state"], "Active")
        self.assertEqual(workspace["region"], "West Europe")
        model = result.inventory["semantic_models"][0]
        self.assertEqual(model["parent_id"], "w1")
        # Table-scoped children must be flattened into model-level lists.
        self.assertEqual(model["columns"], [
            {
                "name": "Amount",
                "table": "factSales",
                "description": None,
                "data_type": "Decimal",
                "hidden": False,
                "column_type": "Data",
                "semantic_role": None,
                "summarize_by": None,
                "synonyms": None,
            }
        ])
        self.assertEqual(model["measures"][0]["name"], "Total Sales")
        self.assertEqual(model["measures"][0]["table"], "factSales")
        self.assertEqual(model["schema_retrieval_error"], "")
        # `relations` is artifact lineage, never model relationships: it must stay unknown.
        self.assertIsNone(model["relationships"])
        self.assertIsNone(model["ai_data_schema"])
        self.assertEqual(result.inventory["reports"][0]["parent_id"], "w1")
        self.assertIs(result.inventory["reports"][0]["semantic_model_reachable"], True)
        self.assertEqual(result.inventory["data_agents"][0]["id"], "a1")
        self.assertEqual(result.inventory["data_agents"][0]["parent_id"], "w1")
        self.assertEqual(result.inventory["tenant"]["fabric_enabled"], True)
        self.assertEqual(result.inventory["tenant"]["agents_enabled"], True)
        self.assertEqual(result.inventory["tenant"]["sensitivity_labels_enabled"], False)
        # An absent setting must stay unknown rather than become a false failure.
        self.assertIsNone(result.inventory["tenant"]["cross_geo_ai_consent"])
        # Capacities must reach the tenant subject, not only the workspace join.
        self.assertEqual(
            result.inventory["tenant"]["capacities"],
            [{"id": "cap-1", "name": "cap-1", "sku": "F8", "state": "Active", "region": "West Europe"}],
        )
        # Two workspaces were listed, only one came back from the scan.
        self.assertEqual(result.inventory["tenant"]["workspaces_total"], 2)
        self.assertEqual(result.inventory["tenant"]["workspaces_scanned"], 1)
        methods = [call[0] for call in calls]
        self.assertEqual(methods.count("POST"), 1)
        self.assertEqual(
            [call[1] for call in calls].count("https://scanner.test/admin/workspaces/scanStatus/scan-1"), 2
        )

    def test_workspace_users_become_role_assignments(self):
        raw = {
            "id": "w1",
            "name": "Synthetic",
            "users": [
                {
                    "displayName": "Finance Admins",
                    "principalType": "Group",
                    "groupUserAccessRight": "Admin",
                },
                {
                    "emailAddress": "person@example.invalid",
                    "principalType": "User",
                    "groupUserAccessRight": "Viewer",
                },
            ],
        }
        workspace = FabricApiCollector.normalize_workspace(raw)
        self.assertEqual(
            workspace["role_assignments"],
            [
                {"role": "Admin", "principal": "Finance Admins", "principal_type": "Group"},
                {"role": "Viewer", "principal": "person@example.invalid", "principal_type": "User"},
            ],
        )

    def test_absent_user_container_stays_unobserved_rather_than_empty(self):
        # No `users` key means the permission surface was never read. Returning []
        # would assert "this workspace has no assignments", which is a different claim.
        workspace = FabricApiCollector.normalize_workspace({"id": "w1", "name": "Synthetic"})
        self.assertIsNone(workspace["role_assignments"])
        observed = FabricApiCollector.normalize_workspace({"id": "w2", "name": "Empty", "users": []})
        self.assertEqual(observed["role_assignments"], [])

    def test_scan_failure_is_recorded_without_inventing_workspaces(self):
        def transport(method, url, body):
            if url.endswith("/tenantsettings"):
                return HttpResponse({"tenantSettings": []}, 200)
            if "/groups?" in url:
                return HttpResponse({"value": [{"id": "w1"}]}, 200)
            if url.endswith("/capacities"):
                return HttpResponse({"value": []}, 200)
            if "/workspaces/getInfo" in url:
                return HttpResponse({"id": "scan-1", "status": "NotStarted"}, 200)
            if url.endswith("/scanStatus/scan-1"):
                return HttpResponse({"id": "scan-1", "status": "Failed"}, 200)
            self.fail(f"unexpected request: {method} {url}")

        result = FabricApiCollector(self.config(), transport, sleep=lambda _: None).collect()

        self.assertEqual(result.inventory["workspaces"], [])
        self.assertTrue(result.errors)

    def test_checkpoint_reuses_completed_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = f"{directory}/checkpoint.json"
            first_calls = []

            def first_transport(method, url, body):
                first_calls.append(url)
                if url.endswith("tenantsettings"):
                    return {"tenantSettings": []}
                if "/groups?" in url:
                    return {"value": []}
                if url.endswith("/capacities"):
                    return {"value": []}
                self.fail(url)

            first = FabricApiCollector(self.config(checkpoint), first_transport).collect()
            self.assertEqual(len(first_calls), 3)

            def no_transport(method, url, body):
                self.fail(f"checkpoint should have avoided {url}")

            second = FabricApiCollector(self.config(checkpoint), no_transport).collect()
            self.assertEqual(len(second.bronze), len(first.bronze))
            with open(checkpoint, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["tenant_id"], "synthetic-tenant")

    def test_throttling_is_raised_not_converted_to_partial_collection(self):
        def transport(method, url, body):
            raise ThrottlingError("retry later")

        with self.assertRaises(ThrottlingError):
            FabricApiCollector(self.config(), transport).collect()

    def _make_batch_transport(self, workspace_ids, *, fail_batch_index=None, throttle_batch_index=None):
        """Build a fake transport serving `len(workspace_ids)` workspaces in batches of 100."""

        def workspace_payload(workspace_id):
            return {"id": workspace_id, "name": workspace_id, "datasets": [], "reports": []}

        def transport(method, url, body):
            if url.endswith("/tenantsettings"):
                return HttpResponse({"tenantSettings": []}, 200)
            if "/groups?" in url:
                return HttpResponse({"value": [{"id": workspace_id} for workspace_id in workspace_ids]}, 200)
            if url.endswith("/capacities"):
                return HttpResponse({"value": []}, 200)
            if "/workspaces/getInfo" in url:
                # Derive the batch index from the request body instead of the URL.
                ids_in_batch = body["workspaces"]
                index = workspace_ids.index(ids_in_batch[0]) // MAX_WORKSPACES_PER_SCAN
                if throttle_batch_index is not None and index == throttle_batch_index:
                    raise ThrottlingError("retry later")
                return HttpResponse({"id": f"scan-{index}", "status": "NotStarted"}, 200)
            if "/scanStatus/scan-" in url:
                scan_id = url.rsplit("/", 1)[-1]
                index = int(scan_id.split("-")[1])
                if fail_batch_index is not None and index == fail_batch_index:
                    return HttpResponse({"id": scan_id, "status": "Failed"}, 200)
                return HttpResponse({"id": scan_id, "status": "Succeeded"}, 200)
            if "/scanResult/scan-" in url:
                scan_id = url.rsplit("/", 1)[-1]
                index = int(scan_id.split("-")[1])
                start = index * MAX_WORKSPACES_PER_SCAN
                batch_ids = workspace_ids[start : start + MAX_WORKSPACES_PER_SCAN]
                return HttpResponse({"workspaces": [workspace_payload(wid) for wid in batch_ids]}, 200)
            self.fail(f"unexpected request: {method} {url}")

        return transport

    def test_throttled_mid_scan_resumes_to_completion_from_checkpoint(self):
        # 150 workspaces = 2 batches of 100 and 50. Batch 1 (the second batch)
        # throttles on the very first attempt.
        workspace_ids = [f"w{i}" for i in range(150)]
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = f"{directory}/checkpoint.json"

            throttling_transport = self._make_batch_transport(workspace_ids, throttle_batch_index=1)
            with self.assertRaises(ThrottlingError):
                FabricApiCollector(
                    self.config(checkpoint), throttling_transport, sleep=lambda _: None
                ).collect()

            # A second, independent collector instance -- as a real caller would
            # create after catching the error -- reuses the same checkpoint path.
            resuming_calls = []

            def resuming_transport(method, url, body):
                resuming_calls.append(url)
                return self._make_batch_transport(workspace_ids)(method, url, body)

            result = FabricApiCollector(
                self.config(checkpoint), resuming_transport, sleep=lambda _: None
            ).collect()

        # Batch 0 (tenant settings, groups, capacities, and the first 100
        # workspaces) must have been served entirely from the checkpoint: only
        # batch 1's getInfo/scanStatus/scanResult calls should hit the network.
        get_info_calls = [call for call in resuming_calls if "/workspaces/getInfo" in call]
        self.assertEqual(len(get_info_calls), 1, "batch 0's getInfo must be replayed from the checkpoint, not re-sent")
        self.assertEqual(result.inventory["tenant"]["workspaces_total"], 150)
        self.assertEqual(result.inventory["tenant"]["workspaces_scanned"], 150)
        self.assertEqual(len(result.inventory["workspaces"]), 150)
        self.assertFalse(result.errors)

    def test_large_tenant_scan_reports_honest_partial_coverage_on_batch_failure(self):
        # 500 workspaces = 5 batches of 100; the middle batch permanently fails.
        workspace_ids = [f"w{i}" for i in range(500)]
        transport = self._make_batch_transport(workspace_ids, fail_batch_index=2)

        result = FabricApiCollector(self.config(), transport, sleep=lambda _: None).collect()

        self.assertEqual(result.inventory["tenant"]["workspaces_total"], 500)
        # Batch 2 (workspaces 200-299) failed, so only 4 of 5 batches' workspaces
        # were actually scanned -- coverage must say so, not silently show 500.
        self.assertEqual(result.inventory["tenant"]["workspaces_scanned"], 400)
        self.assertEqual(len(result.inventory["workspaces"]), 400)
        scanned_ids = {workspace["id"] for workspace in result.inventory["workspaces"]}
        self.assertFalse(scanned_ids & {f"w{i}" for i in range(200, 300)})
        self.assertTrue(result.errors)
        self.assertTrue(any("Failed" in error["message"] for error in result.errors))

    def test_getinfo_quota_throttles_proactively_before_the_hourly_ceiling(self):
        # Six batches (600 workspaces) with a quota of 2 calls/hour: the third
        # getInfo call must wait for the first call to fall out of the rolling
        # window rather than firing immediately.
        workspace_ids = [f"w{i}" for i in range(300)]
        transport = self._make_batch_transport(workspace_ids)
        sleeps = []
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        def sleep(seconds):
            sleeps.append(seconds)
            clock_time[0] += seconds

        import fabric_iq.collectors.fabric_api as fabric_api_module

        original_cap = fabric_api_module.MAX_GETINFO_CALLS_PER_HOUR
        fabric_api_module.MAX_GETINFO_CALLS_PER_HOUR = 2
        try:
            collector = FabricApiCollector(self.config(), transport, sleep=sleep, clock=clock)
            result = collector.collect()
        finally:
            fabric_api_module.MAX_GETINFO_CALLS_PER_HOUR = original_cap

        # 3 batches of 100 => 3 getInfo calls, cap of 2/hour => exactly one wait.
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 0)
        self.assertEqual(result.inventory["tenant"]["workspaces_scanned"], 300)


if __name__ == "__main__":
    unittest.main()
