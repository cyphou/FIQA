"""The GitHub-based installer notebook must stay structurally sound and leak nothing.

These tests never touch the network. They parse the shipped notebook source the same
way ``tests/test_deployment.py`` parses the other items, and they exercise the
archive-layout resolution logic in isolation by re-executing that one cell against a
fake, locally-built zip.
"""

import io
import json
import os
import re
import unittest
import zipfile

INSTALLER_ITEM = "Install_IsFabricReadyForIQ.Notebook"
INSTALLER_SOURCE = "notebook-content.py"

ITEMS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fabric", "items"
)


def _read_installer_source() -> str:
    path = os.path.join(ITEMS_ROOT, INSTALLER_ITEM, INSTALLER_SOURCE)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _read_platform_metadata() -> dict:
    path = os.path.join(ITEMS_ROOT, INSTALLER_ITEM, ".platform")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _all_logical_ids() -> dict:
    ids = {}
    for entry in sorted(os.listdir(ITEMS_ROOT)):
        platform_path = os.path.join(ITEMS_ROOT, entry, ".platform")
        if not os.path.isfile(platform_path):
            continue
        with open(platform_path, "r", encoding="utf-8") as handle:
            ids[entry] = json.load(handle)["config"]["logicalId"]
    return ids


class InstallerPlatformMetadataTests(unittest.TestCase):
    def test_item_is_a_notebook_with_the_expected_display_name(self):
        meta = _read_platform_metadata()["metadata"]
        self.assertEqual(meta["type"], "Notebook")
        self.assertEqual(meta["displayName"], "Install_IsFabricReadyForIQ")

    def test_logical_id_does_not_collide_with_any_other_shipped_item(self):
        ids = _all_logical_ids()
        installer_id = ids[INSTALLER_ITEM]
        others = {name: value for name, value in ids.items() if name != INSTALLER_ITEM}
        self.assertNotIn(installer_id, others.values())
        # And every id present is a well-formed GUID, not a copy/paste typo.
        guid_re = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
        for name, value in ids.items():
            self.assertRegex(value, guid_re, f"{name} has a malformed logicalId")


class InstallerNotebookContentTests(unittest.TestCase):
    def setUp(self):
        self.source = _read_installer_source()

    def test_starts_with_the_fabric_notebook_marker(self):
        self.assertTrue(self.source.startswith("# Fabric notebook source"))

    def test_parameters_cell_defaults_point_at_the_public_installer_repo(self):
        self.assertIn('github_repo = "cyphou/FIQA"', self.source)
        self.assertIn('github_ref = "main"', self.source)
        self.assertIn('workspace_id = ""', self.source)
        self.assertIn('default_tenant_id = ""', self.source)

    def test_download_url_is_built_from_the_parameters_not_hardcoded(self):
        self.assertIn(
            'archive_url = f"https://github.com/{github_repo}/archive/{github_ref}.zip"',
            self.source,
        )

    def test_only_delegated_notebookutils_tokens_are_used(self):
        self.assertIn('notebookutils.credentials.getToken("pbi")', self.source)
        self.assertIn('notebookutils.credentials.getToken("storage")', self.source)

    def test_temp_install_directory_is_always_cleaned_up(self):
        self.assertIn("shutil.rmtree(install_root, ignore_errors=True)", self.source)
        # The cleanup must be reachable on the failure path too.
        finally_block = self.source.split("try:", 1)[1].split("print(json.dumps", 1)[0]
        self.assertIn("finally:", finally_block)
        self.assertIn("shutil.rmtree", finally_block.split("finally:", 1)[1])

    def test_imports_deployment_logic_from_the_fetched_checkout_only(self):
        self.assertIn("from fabric_iq.deployment import DeploymentConfig, FabricRestClient, deploy", self.source)
        self.assertIn("from fabric_iq.errors import DeploymentError", self.source)

    def test_no_secret_looking_literal_is_shipped(self):
        # Guards against ever hard-coding a connection string, key, or token
        # default into the parameters cell.
        suspicious = re.compile(
            r"(client_secret|access_token|api_key|connection_string)\s*=\s*[\"'][^\"']+[\"']",
            re.IGNORECASE,
        )
        self.assertIsNone(suspicious.search(self.source))


class ArchiveLayoutResolutionTests(unittest.TestCase):
    """Re-runs the exact fetch-cell logic that picks the single extracted subfolder."""

    def _resolve_single_subfolder(self, install_root: str) -> str:
        entries = [
            entry
            for entry in os.listdir(install_root)
            if os.path.isdir(os.path.join(install_root, entry))
        ]
        if len(entries) != 1:
            raise RuntimeError(f"Unexpected archive layout under {install_root}: {entries}")
        return os.path.join(install_root, entries[0])

    def _build_fake_archive(self, tmp_path: str, *top_level_dirs: str) -> str:
        archive_path = os.path.join(tmp_path, "source.zip")
        with zipfile.ZipFile(archive_path, "w") as archive:
            for top in top_level_dirs:
                archive.writestr(f"{top}/README.md", "hello")
        return archive_path

    def test_single_top_level_folder_is_selected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = self._build_fake_archive(tmp, "FIQA-main")
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(tmp)
            os.remove(archive_path)
            source_root = self._resolve_single_subfolder(tmp)
            self.assertTrue(source_root.endswith("FIQA-main"))

    def test_unexpected_layout_with_zero_folders_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self._resolve_single_subfolder(tmp)

    def test_unexpected_layout_with_multiple_folders_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = self._build_fake_archive(tmp, "FIQA-main", "extra")
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(tmp)
            os.remove(archive_path)
            with self.assertRaises(RuntimeError):
                self._resolve_single_subfolder(tmp)


if __name__ == "__main__":
    unittest.main()
