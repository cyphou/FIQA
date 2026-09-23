"""Executable evidence-sink hygiene (Phase 5 release gate criterion 9).

Two kinds of test live here. The *real-tree* tests assert the invariant the
release gate states: in this repository, every writer destination resolves to a
committed ignore rule, every tracked file stays trackable, and no tracked file
carries a real identifier. The *synthetic* tests build a throwaway git
repository and prove the checker actually fails when those invariants break --
a checker that only ever sees a clean tree has never been shown to detect
anything.

No fixture here is captured from a tenant. Identifier-shaped strings are
assembled at runtime from fragments, so this file itself stays clean under its
own scanner.
"""

import io
import contextlib
import os
import subprocess
import tempfile
import unittest

from scripts.check_evidence_sinks import (
    ALLOWED_EMAIL_DOMAINS,
    GOLD_TABLES,
    _is_placeholder_guid,
    audit,
    check_sinks,
    check_tracked_not_shadowed,
    documented_sinks,
    main,
    scan_tracked_identifiers,
    tracked_files,
    writer_sinks,
)
from tests.helpers import REPO_ROOT


def tenant_shaped_guid() -> str:
    """A GUID that looks like a tenant issued it, assembled so no literal exists."""
    return "-".join(["3f2b9c71", "4d2e", "4a11", "9b33", "7c5d1e2f4a6b"])


def tenant_shaped_upn() -> str:
    return "admin" + "@" + "fabrikam-not-reserved.com"


def tenant_shaped_host() -> str:
    return "fabrikam" + ".onmicrosoft.com"


def _git(root, *args):
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _write(root, relative, content, mode="w"):
    absolute = os.path.join(root, relative.replace("/", os.sep))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    encoding = None if "b" in mode else "utf-8"
    with open(absolute, mode, encoding=encoding) as handle:
        handle.write(content)


class TempRepoCase(unittest.TestCase):
    """A synthetic git repository, so failure paths never depend on this checkout."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        _git(self.root, "init", "-q")

    def track(self, relative, content, mode="w"):
        """Write a file and put it in the index (no commit: the index is enough)."""
        _write(self.root, relative, content, mode)
        _git(self.root, "add", "--", relative)

    def ignore(self, *rules):
        _write(self.root, ".gitignore", "\n".join(rules) + "\n")
        _git(self.root, "add", "--", ".gitignore")


class PlaceholderGuidTests(unittest.TestCase):
    def test_zero_and_counter_guids_are_placeholders(self):
        for guid in (
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000042",
            "11111111-2222-3333-4444-555555555555",
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ):
            with self.subTest(guid=guid):
                self.assertTrue(_is_placeholder_guid(guid))

    def test_a_tenant_shaped_guid_is_not_a_placeholder(self):
        self.assertFalse(_is_placeholder_guid(tenant_shaped_guid()))


class SinkCheckTests(TempRepoCase):
    def test_a_destination_with_no_rule_is_reported(self):
        self.ignore("artifacts/")

        problems = check_sinks(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("powerbi_report/data/MartRunSummary.csv", problems[0])
        self.assertIn("no ignore rule", problems[0])

    def test_a_destination_covered_by_a_rule_passes(self):
        self.ignore("artifacts/", "powerbi_report/", "*.jsonl")

        problems = check_sinks(
            self.root,
            [
                ("artifacts/run_assessment.json", "--out default"),
                ("powerbi_report/data/MartRunSummary.csv", "marts"),
                ("anywhere/run.jsonl", "NDJSON"),
            ],
        )

        self.assertEqual(problems, [])

    def test_a_destination_re_included_by_a_negation_rule_is_reported(self):
        self.ignore("*.jsonl", "!keepme/*.jsonl")

        problems = check_sinks(self.root, [("keepme/run.jsonl", "Gold NDJSON")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("negation", problems[0])

    def test_a_rule_that_is_not_committed_does_not_count(self):
        # .git/info/exclude protects one clone only. A teammate who runs the
        # documented command still commits the evidence.
        self.ignore("artifacts/")
        _write(self.root, ".git/info/exclude", "powerbi_report/\n")

        problems = check_sinks(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("not a committed .gitignore", problems[0])


class ShadowedTrackedFileTests(TempRepoCase):
    def test_a_tracked_file_swallowed_by_a_broad_rule_is_reported(self):
        # The regression risk of covering every mart with `*.jsonl`.
        self.track("examples/sample_tenant/fixture.jsonl", '{"id": "sm-1"}\n')
        self.ignore("*.jsonl")

        problems = check_tracked_not_shadowed(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("examples/sample_tenant/fixture.jsonl", problems[0])
        self.assertIn("shadowed", problems[0])

    def test_an_explicit_re_inclusion_keeps_a_fixture_trackable(self):
        self.track("examples/sample_tenant/fixture.jsonl", '{"id": "sm-1"}\n')
        self.ignore("*.jsonl", "!examples/**/*.jsonl")

        self.assertEqual(check_tracked_not_shadowed(self.root), [])

    def test_an_unshadowed_tree_reports_nothing(self):
        self.track("README.md", "# synthetic\n")
        self.ignore("artifacts/")

        self.assertEqual(check_tracked_not_shadowed(self.root), [])


class IdentifierScanTests(TempRepoCase):
    def test_a_tenant_shaped_guid_upn_and_host_are_all_reported(self):
        self.track(
            "docs/example.md",
            f"tenant {tenant_shaped_guid()}\ncontact {tenant_shaped_upn()}\nhost {tenant_shaped_host()}\n",
        )

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any("GUID" in p for p in problems), problems)
        self.assertTrue(any("address" in p for p in problems), problems)
        self.assertTrue(any("tenant host" in p for p in problems), problems)
        self.assertTrue(all(p.startswith("docs/example.md:") for p in problems), problems)

    def test_placeholders_and_reserved_domains_pass(self):
        self.track(
            "docs/example.md",
            "id 00000000-0000-0000-0000-000000000001\n"
            "owner person@example.invalid\n"
            "other someone@example.com\n",
        )

        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_an_untracked_file_is_not_scanned(self):
        # Only the index can leak. An untracked scratch file is the user's business.
        _write(self.root, "scratch.md", f"tenant {tenant_shaped_guid()}\n")
        self.track("README.md", "# synthetic\n")

        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_an_explicit_allowlist_entry_is_honoured(self):
        guid = tenant_shaped_guid()
        self.track("docs/example.md", f"id {guid}\n")

        self.assertEqual(
            scan_tracked_identifiers(self.root, allowed_guids={guid: "synthetic sample"}), []
        )

    def test_an_allowlisted_path_is_skipped_entirely(self):
        self.track("docs/example.md", f"id {tenant_shaped_guid()}\n")

        self.assertEqual(
            scan_tracked_identifiers(self.root, allowed_paths={"docs/example.md": "why"}), []
        )

    def test_a_domain_outside_the_reserved_set_is_reported(self):
        self.assertNotIn("fabrikam-not-reserved.com", ALLOWED_EMAIL_DOMAINS)
        self.track("docs/example.md", f"contact {tenant_shaped_upn()}\n")

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("fabrikam-not-reserved.com", problems[0])

    def test_a_binary_file_is_skipped_rather_than_crashing_the_scan(self):
        self.track("assets/logo.bin", b"\xff\xfe\x00\x01binary", mode="wb")

        self.assertEqual(scan_tracked_identifiers(self.root), [])


class AuditTests(TempRepoCase):
    def test_audit_reports_every_failing_check_separately(self):
        self.track("docs/example.md", f"tenant {tenant_shaped_guid()}\n")
        self.track("examples/fixture.jsonl", "{}\n")
        self.ignore("*.jsonl")

        problems = audit(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual(set(problems), {"sinks", "shadowed", "identifiers"})
        for check in ("sinks", "shadowed", "identifiers"):
            with self.subTest(check=check):
                self.assertTrue(problems[check], f"{check} should have failed")

    def test_audit_is_clean_when_every_invariant_holds(self):
        self.track("docs/example.md", "id 00000000-0000-0000-0000-000000000000\n")
        self.ignore("artifacts/", "powerbi_report/")

        problems = audit(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual({k: v for k, v in problems.items() if v}, {})


class RealTreeTests(unittest.TestCase):
    """The gate itself: these assert the state of this repository."""

    def test_every_writer_destination_resolves_to_a_committed_ignore_rule(self):
        self.assertEqual(check_sinks(REPO_ROOT, writer_sinks()), [])

    def test_every_documented_output_example_resolves_to_a_rule(self):
        self.assertEqual(check_sinks(REPO_ROOT, documented_sinks(REPO_ROOT)), [])

    def test_the_documented_scan_actually_finds_the_known_examples(self):
        # Guards the scan itself: a regex that matches nothing would pass the
        # previous test while checking nothing at all.
        found = dict(documented_sinks(REPO_ROOT))
        for expected in ("artifacts/", "powerbi_report/", "lakehouse/"):
            with self.subTest(path=expected):
                self.assertIn(expected, found)

    def test_every_gold_mart_is_covered_by_a_checked_destination(self):
        paths = " ".join(path for path, _ in writer_sinks())
        for table in GOLD_TABLES:
            with self.subTest(table=table):
                self.assertIn(f"{table}.csv", paths)
                self.assertIn(f"gold/{table}/", paths)

    def test_no_tracked_file_is_shadowed_by_an_ignore_rule(self):
        self.assertEqual(check_tracked_not_shadowed(REPO_ROOT), [])

    def test_every_tracked_file_is_still_trackable(self):
        # The same invariant stated as a count: broad patterns must not silently
        # drop files out of `git add`.
        files = tracked_files(REPO_ROOT)
        self.assertGreater(len(files), 50)
        self.assertEqual(len(check_tracked_not_shadowed(REPO_ROOT)), 0)

    def test_tracked_content_carries_no_real_identifier(self):
        self.assertEqual(scan_tracked_identifiers(REPO_ROOT), [])

    def test_the_check_exits_zero_on_a_clean_tree(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([])
        self.assertEqual(code, 0, buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
