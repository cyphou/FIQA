"""Tests guarding the Gold mart schema against silent drift.

These tests exist because of a real bug: a mart with zero rows for a run wrote an
empty NDJSON file, Spark's schema inference on that file produced a DataFrame with no
columns, and the notebook silently skipped ``saveAsTable`` for it -- so the Delta
table never existed and the Direct Lake report failed with "Invalid object name" the
moment a visual queried it. The fix builds an explicit, typed empty frame from
``GOLD_SCHEMAS`` instead of skipping. These tests make sure ``GOLD_SCHEMAS`` never
drifts out of sync with ``GOLD_TABLES`` or with the columns ``gold_mart_rows``
actually produces.
"""

import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fabric_iq import lakehouse as lakehouse_module
from fabric_iq.errors import PersistenceError
from fabric_iq.lakehouse import (
    BRONZE,
    GOLD,
    SILVER,
    GOLD_SCHEMAS,
    GOLD_TABLES,
    LakehouseRetentionPruner,
    LakehouseWriter,
    _dir_fd_deletion_supported,
    gold_mart_rows,
)
from fabric_iq.remediation import build_backlog
from fabric_iq.scoring import assess
from tests.helpers import minimal_inventory, ready_model, ready_tenant

_VALID_TYPES = {"string", "double", "long", "boolean"}


class GoldSchemasShapeTests(unittest.TestCase):
    def test_every_gold_table_has_a_schema(self):
        self.assertEqual(set(GOLD_SCHEMAS.keys()), set(GOLD_TABLES))

    def test_schemas_only_use_the_notebooks_known_types(self):
        for table, fields in GOLD_SCHEMAS.items():
            for name, dtype in fields:
                self.assertIn(
                    dtype, _VALID_TYPES, f"{table}.{name} has unsupported type {dtype!r}"
                )

    def test_schemas_have_no_duplicate_columns(self):
        for table, fields in GOLD_SCHEMAS.items():
            names = [name for name, _ in fields]
            self.assertEqual(len(names), len(set(names)), f"{table} has duplicate columns")


class GoldSchemasMatchRowsTests(unittest.TestCase):
    """``GOLD_SCHEMAS`` columns must match what the row builders actually emit."""

    def _assert_columns_match(self, table, rows):
        expected = {name for name, _ in GOLD_SCHEMAS[table]}
        if not rows:
            # An empty mart is exactly the case GOLD_SCHEMAS exists to cover; there
            # are no row keys to compare against, but the schema itself must still
            # be present (covered by test_every_gold_table_has_a_schema).
            return
        actual = set(rows[0].keys())
        self.assertEqual(
            actual,
            expected,
            f"{table}: row keys {sorted(actual)} != GOLD_SCHEMAS {sorted(expected)}",
        )

    def test_populated_run_columns_match_schema(self):
        # A run with a scored semantic model and a blocking tenant finding populates
        # every mart, including MartObjectReadiness and MartBlockingFindings.
        inventory = minimal_inventory(
            tenant=ready_tenant(fabric_enabled=False),
            semantic_models=[ready_model()],
        )
        run = assess(inventory, run_id="run_populated")
        backlog = build_backlog(run)
        marts = gold_mart_rows(run, backlog, run_id="run_populated")

        for table in GOLD_TABLES:
            self._assert_columns_match(table, marts[table])
        # Sanity check the fixture actually exercised the marts we care about.
        self.assertTrue(marts["MartObjectReadiness"])
        self.assertTrue(marts["MartBlockingFindings"])
        self.assertTrue(marts["MartRemediationBacklog"])

    def test_clean_run_leaves_some_marts_empty_but_still_schema_covered(self):
        # A healthy tenant with no scanned objects: MartObjectReadiness,
        # MartBlockingFindings and MartRemediationBacklog are all legitimately
        # empty -- exactly the scenario that used to make the notebook skip
        # creating the Delta table.
        run = assess(minimal_inventory(), run_id="run_clean")
        backlog = build_backlog(run, include_partial=False)
        marts = gold_mart_rows(run, backlog, run_id="run_clean")

        self.assertEqual(marts["MartObjectReadiness"], [])
        self.assertEqual(marts["MartBlockingFindings"], [])
        self.assertEqual(marts["MartRemediationBacklog"], [])
        # Every table -- populated or not -- must still have a schema to fall back on.
        for table in GOLD_TABLES:
            self.assertIn(table, GOLD_SCHEMAS)
            self._assert_columns_match(table, marts[table])


class LakehouseRetentionTests(unittest.TestCase):
    NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    def _write_all_layers(self, root, run_id, completed_at):
        inventory = minimal_inventory()
        run = replace(assess(inventory, run_id=run_id), completed_at=completed_at)
        backlog = build_backlog(run)
        written = LakehouseWriter(root=root, run_id=run_id).write_run(
            run,
            backlog,
            inventory=inventory,
            bronze=[{"endpoint": "synthetic", "payload": {"value": 1}}],
        )
        return inventory, run, backlog, written

    @staticmethod
    def _partition_paths(written):
        return [
            written[BRONZE],
            *written[SILVER],
            *written[GOLD].values(),
        ]

    def _write_expired_partition_with_manifest(self, root, run_id="expired_manifest"):
        completed_at = (self.NOW - timedelta(days=800)).isoformat()
        partition_dir = os.path.join(root, BRONZE, "evidence")
        os.makedirs(partition_dir, exist_ok=True)
        partition_path = os.path.join(partition_dir, f"{run_id}.jsonl")
        with open(partition_path, "w", encoding="utf-8") as handle:
            handle.write("{}\n")

        manifest_dir = os.path.join(root, "manifests")
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, f"{run_id}.json")
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "completed_at": completed_at,
            "written_at": completed_at,
            "retention_timestamp": completed_at,
            "partitions": [
                {
                    "layer": BRONZE,
                    "table": "evidence",
                    "path": f"bronze/evidence/{run_id}.jsonl",
                }
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return partition_path, manifest_path, manifest

    def _redirect_directory_or_skip(self, link_path, target_path):
        if os.name == "nt":
            completed = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", link_path, target_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("cannot create a Windows directory junction in this environment")
            return
        try:
            os.symlink(target_path, link_path, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create a directory symlink in this environment: {exc}")

    def _file_symlink_or_skip(self, link_path, target_path):
        try:
            os.symlink(target_path, link_path)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create a file symlink in this environment: {exc}")

    def test_write_run_persists_lifecycle_manifest(self):
        completed_at = "2026-09-20T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "manifested", completed_at)
            with open(written["manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)

            expected_paths = {
                os.path.relpath(path, tmp).replace(os.sep, "/")
                for path in self._partition_paths(written)
            }
            declared_paths = {partition["path"] for partition in manifest["partitions"]}

        self.assertEqual(manifest["run_id"], "manifested")
        self.assertEqual(manifest["completed_at"], completed_at)
        self.assertEqual(manifest["retention_timestamp"], completed_at)
        self.assertTrue(manifest["written_at"])
        self.assertEqual(declared_paths, expected_paths)

    def test_write_run_manifest_falls_back_to_written_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "no_completion", "")
            with open(written["manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)

        self.assertEqual(manifest["completed_at"], "")
        self.assertEqual(manifest["retention_timestamp"], manifest["written_at"])

    def test_partial_write_run_retains_manifested_lifecycle_metadata(self):
        class FailingWriter(LakehouseWriter):
            def _write_ndjson(self, layer, table, rows):
                path = super()._write_ndjson(layer, table, rows)
                if layer == BRONZE:
                    raise PersistenceError("synthetic partial write")
                return path

        inventory = minimal_inventory()
        run = replace(
            assess(inventory, run_id="partial"),
            completed_at="2026-09-20T12:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as tmp:
            writer = FailingWriter(tmp, "partial")
            with self.assertRaisesRegex(PersistenceError, "synthetic partial write"):
                writer.write_run(
                    run,
                    build_backlog(run),
                    inventory=inventory,
                    bronze=[{"endpoint": "synthetic"}],
                )

            manifest_path = os.path.join(tmp, "manifests", "partial.json")
            with open(manifest_path, encoding="utf-8") as handle:
                manifest = json.load(handle)

        self.assertEqual(manifest["retention_timestamp"], run.completed_at)
        self.assertEqual(
            manifest["partitions"],
            [
                {
                    "layer": BRONZE,
                    "table": "evidence",
                    "path": "bronze/evidence/partial.jsonl",
                }
            ],
        )

    def test_unexpired_partitions_survive_prune(self):
        completed_at = (self.NOW - timedelta(days=30)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "unexpired", completed_at)
            paths = self._partition_paths(written)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.pruned)
            self.assertFalse(result.failures)
            self.assertEqual(len(result.kept), len(paths))
            self.assertTrue(all(os.path.exists(path) for path in paths))

    def test_expired_partitions_are_deleted(self):
        completed_at = (self.NOW - timedelta(days=731)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "expired", completed_at)
            paths = self._partition_paths(written)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.failures)
            self.assertEqual(len(result.pruned), len(paths))
            self.assertFalse(result.kept)
            self.assertTrue(all(not os.path.exists(path) for path in paths))

    def test_partition_without_manifest_is_reported_and_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = os.path.join(tmp, BRONZE, "evidence")
            os.makedirs(directory)
            orphan_path = os.path.join(directory, "orphan.jsonl")
            with open(orphan_path, "w", encoding="utf-8") as handle:
                handle.write("{}\n")

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(orphan_path))
            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].run_id, "orphan")
            self.assertIn("manifest is missing", result.failures[0].reason)

    def test_invalid_manifest_timestamp_is_reported_and_not_deleted(self):
        completed_at = (self.NOW - timedelta(days=800)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "invalid_time", completed_at)
            paths = self._partition_paths(written)
            with open(written["manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)
            manifest["retention_timestamp"] = "not-a-timestamp"
            with open(written["manifest"], "w", encoding="utf-8") as handle:
                json.dump(manifest, handle)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), len(paths))
            self.assertTrue(all(os.path.exists(path) for path in paths))
            self.assertTrue(
                all("invalid retention_timestamp" in failure.reason for failure in result.failures)
            )

    def test_redirected_layer_cannot_delete_outside_root(self):
        run_id = "junction_escape"
        completed_at = (self.NOW - timedelta(days=800)).isoformat()
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            manifest_dir = os.path.join(tmp, "manifests")
            os.makedirs(manifest_dir)
            with open(os.path.join(manifest_dir, f"{run_id}.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "completed_at": completed_at,
                        "written_at": completed_at,
                        "retention_timestamp": completed_at,
                        "partitions": [
                            {
                                "layer": BRONZE,
                                "table": "evidence",
                                "path": f"bronze/evidence/{run_id}.jsonl",
                            }
                        ],
                    },
                    handle,
                )
            external_bronze = os.path.join(external, "external_bronze")
            external_table = os.path.join(external_bronze, "evidence")
            os.makedirs(external_table)
            external_partition = os.path.join(external_table, f"{run_id}.jsonl")
            with open(external_partition, "w", encoding="utf-8") as handle:
                handle.write("{}\n")
            self._redirect_directory_or_skip(os.path.join(tmp, BRONZE), external_bronze)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(external_partition))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("reparse point", result.failures[0].reason)

    def test_dir_fd_support_gate_uses_unlink_capability(self):
        supported_functions = {os.stat, os.unlink}
        with (
            mock.patch.object(lakehouse_module.os, "supports_dir_fd", supported_functions),
            mock.patch.object(lakehouse_module.os, "O_DIRECTORY", 0, create=True),
        ):
            self.assertTrue(_dir_fd_deletion_supported())

        remove_only_functions = {os.stat, os.remove}
        with (
            mock.patch.object(lakehouse_module.os, "supports_dir_fd", remove_only_functions),
            mock.patch.object(lakehouse_module.os, "O_DIRECTORY", 0, create=True),
        ):
            self.assertFalse(_dir_fd_deletion_supported())

    @unittest.skipUnless(_dir_fd_deletion_supported(), "dir_fd deletion is not supported")
    def test_dir_fd_delete_reports_table_swap_race_without_external_delete(self):
        run_id = "dir_fd_directory_swap"
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            partition_path, _, _ = self._write_expired_partition_with_manifest(tmp, run_id)
            table_path = os.path.dirname(partition_path)
            moved_table_path = f"{table_path}_moved"
            external_partition = os.path.join(external, f"{run_id}.jsonl")
            with open(external_partition, "w", encoding="utf-8") as handle:
                handle.write("external file must survive\n")

            original_stat = lakehouse_module.os.stat
            partition_name = os.path.basename(partition_path)
            race_injected = False

            def racing_stat(path, *args, **kwargs):
                nonlocal race_injected
                if (
                    path == partition_name
                    and kwargs.get("dir_fd") is not None
                    and not race_injected
                ):
                    race_injected = True
                    os.rename(table_path, moved_table_path)
                    try:
                        os.symlink(external, table_path, target_is_directory=True)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest(f"cannot create a directory symlink: {exc}")
                return original_stat(path, *args, **kwargs)

            with (
                mock.patch.object(
                    lakehouse_module, "_dir_fd_deletion_supported", return_value=True
                ),
                mock.patch.object(lakehouse_module.os, "stat", side_effect=racing_stat),
            ):
                result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(race_injected)
            self.assertTrue(os.path.exists(external_partition))
            self.assertFalse(os.path.exists(os.path.join(moved_table_path, partition_name)))
            self.assertEqual(len(result.pruned), 1)
            self.assertFalse(result.failures)

    def test_fallback_delete_reports_partition_swap_race_and_deletes_nothing(self):
        """The non-``dir_fd`` deletion path must refuse to remove a swapped partition.

        On Windows this fallback is the only deletion path, so the ``_same_file``
        check between ``partition_stat`` and the pre-delete ``delete_stat`` is the
        sole protection against the partition being replaced between authorisation
        and ``os.remove``. The swap is injected at the moment the pre-delete
        ``_safe_existing_path`` re-check reads the path, so ``delete_stat`` describes
        a *different* file than the one retention actually authorised; the guard must
        fire, nothing may be pruned, and the substituted file must survive on disk.
        """
        run_id = "fallback_partition_swap"
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            partition_path, _, _ = self._write_expired_partition_with_manifest(tmp, run_id)
            original_inode = os.stat(partition_path).st_ino
            substitute_source = os.path.join(external, "substitute.jsonl")
            substitute_marker = "substituted file must survive\n"
            with open(substitute_source, "w", encoding="utf-8") as handle:
                handle.write(substitute_marker)

            original_stat = lakehouse_module.os.stat
            target = os.path.normcase(os.path.abspath(partition_path))
            partition_stat_calls = 0
            race_injected = False

            def racing_stat(path, *args, **kwargs):
                nonlocal partition_stat_calls, race_injected
                if (
                    isinstance(path, (str, bytes, os.PathLike))
                    and kwargs.get("dir_fd") is None
                    and os.path.normcase(os.path.abspath(os.fspath(path))) == target
                ):
                    partition_stat_calls += 1
                    # Call 1 authorises the partition; call 2 is the pre-delete
                    # re-check that produces ``delete_stat``. Swap the file in
                    # between so the re-check observes the substituted inode.
                    if partition_stat_calls == 2 and not race_injected:
                        race_injected = True
                        os.replace(substitute_source, partition_path)
                return original_stat(path, *args, **kwargs)

            with (
                mock.patch.object(
                    lakehouse_module, "_dir_fd_deletion_supported", return_value=False
                ),
                mock.patch.object(lakehouse_module.os, "stat", side_effect=racing_stat),
            ):
                result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(race_injected, "the swap hook never fired; the test proves nothing")
            self.assertTrue(
                os.path.exists(partition_path),
                "the substituted file was deleted without authorisation",
            )
            with open(partition_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), substitute_marker)
            self.assertNotEqual(os.stat(partition_path).st_ino, original_inode)
            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), 1)
            failure = result.failures[0]
            self.assertEqual(failure.reason, "partition changed during retention check")
            self.assertEqual(failure.run_id, run_id)
            self.assertEqual(failure.path, partition_path)

    def test_symlinked_manifest_file_is_reported_and_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            partition_path, manifest_path, manifest = self._write_expired_partition_with_manifest(
                tmp, "manifest_symlink"
            )
            external_manifest = os.path.join(external, "external_manifest.json")
            with open(external_manifest, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle)
            os.remove(manifest_path)
            self._file_symlink_or_skip(manifest_path, external_manifest)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(partition_path))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("run manifest", result.failures[0].reason)
            self.assertIn("reparse point", result.failures[0].reason)

    def test_redirected_manifest_directory_is_reported_and_not_trusted(self):
        run_id = "manifest_directory_redirect"
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            partition_path, manifest_path, manifest = self._write_expired_partition_with_manifest(tmp, run_id)
            os.remove(manifest_path)
            os.rmdir(os.path.join(tmp, "manifests"))
            with open(os.path.join(external, f"{run_id}.json"), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle)
            self._redirect_directory_or_skip(os.path.join(tmp, "manifests"), external)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(partition_path))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("run manifest directory", result.failures[0].reason)
            self.assertIn("reparse point", result.failures[0].reason)

    def test_bool_manifest_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            partition_path, manifest_path, manifest = self._write_expired_partition_with_manifest(
                tmp, "bool_schema"
            )
            manifest["schema_version"] = True
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(partition_path))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("unsupported schema version", result.failures[0].reason)

    def test_duplicate_manifest_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            partition_path, manifest_path, manifest = self._write_expired_partition_with_manifest(
                tmp, "duplicate_keys"
            )
            manifest_json = json.dumps(manifest)
            manifest_json = manifest_json.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
            with open(manifest_path, "w", encoding="utf-8") as handle:
                handle.write(manifest_json)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(partition_path))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("duplicate JSON key", result.failures[0].reason)

    def test_mismatched_manifest_path_invalidates_the_whole_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            partition_path, manifest_path, manifest = self._write_expired_partition_with_manifest(
                tmp, "mismatched_path"
            )
            manifest["partitions"].append(
                {
                    "layer": BRONZE,
                    "table": "evidence",
                    "path": "bronze/evidence/not_the_manifest_run.jsonl",
                }
            )
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertTrue(os.path.exists(partition_path))
            self.assertFalse(result.pruned)
            self.assertEqual(len(result.failures), 1)
            self.assertIn("path does not match", result.failures[0].reason)

    def test_non_directory_table_entry_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, BRONZE))
            stray_path = os.path.join(tmp, BRONZE, "stray_file")
            with open(stray_path, "w", encoding="utf-8") as handle:
                handle.write("not a table")

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].path, stray_path)
            self.assertIn("not a directory", result.failures[0].reason)

    def test_unreadable_table_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            table_path = os.path.join(tmp, BRONZE, "evidence")
            os.makedirs(table_path)
            original_scandir = os.scandir

            def raising_scandir(path):
                if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(table_path)):
                    raise PermissionError("synthetic denied")
                return original_scandir(path)

            with mock.patch("os.scandir", side_effect=raising_scandir):
                result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].path, table_path)
            self.assertIn("cannot list table", result.failures[0].reason)

    def test_non_regular_partition_entry_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            table_path = os.path.join(tmp, BRONZE, "evidence")
            os.makedirs(table_path)
            partition_dir = os.path.join(table_path, "directory_partition.jsonl")
            os.makedirs(partition_dir)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.pruned)
            self.assertFalse(result.kept)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].path, partition_dir)
            self.assertIn("not a regular file", result.failures[0].reason)

    def test_normal_write_paths_never_delete_an_old_run(self):
        old_completed_at = (self.NOW - timedelta(days=1000)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, old_written = self._write_all_layers(tmp, "old_run", old_completed_at)
            old_paths = self._partition_paths(old_written)

            inventory = minimal_inventory()
            run = assess(inventory, run_id="current_run")
            backlog = build_backlog(run)
            writer = LakehouseWriter(tmp, "current_run")
            writer.write_bronze([{"endpoint": "synthetic"}])
            writer.write_silver(inventory)
            writer.write_gold(run, backlog)
            writer.write_run(run, backlog, inventory=inventory, bronze=[])

            self.assertTrue(all(os.path.exists(path) for path in old_paths))

    def test_each_layer_uses_its_own_retention_cutoff(self):
        completed_at = (self.NOW - timedelta(days=100)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, written = self._write_all_layers(tmp, "layer_cutoffs", completed_at)

            result = LakehouseRetentionPruner(tmp, self.NOW).prune()

            self.assertFalse(result.failures)
            self.assertEqual({partition.layer for partition in result.pruned}, {BRONZE})
            self.assertEqual(
                {partition.layer for partition in result.kept},
                {SILVER, GOLD},
            )
            self.assertFalse(os.path.exists(written[BRONZE]))
            self.assertTrue(all(os.path.exists(path) for path in written[SILVER]))
            self.assertTrue(all(os.path.exists(path) for path in written[GOLD].values()))


if __name__ == "__main__":
    unittest.main()
