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
    _is_plausible_destination,
    audit,
    check_ignore,
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


def flag_example(flag: str, value: str) -> str:
    """Build a ``--flag value`` example at runtime.

    Written literally, these fixtures would be scraped out of *this* tracked file
    by ``documented_sinks`` and checked against the real ignore rules -- the file
    would document destinations nobody writes to. Same discipline as the
    identifier helpers above: assemble, never spell out.
    """
    return "--" + flag + " " + value


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

    def ignore_bytes(self, raw):
        """Write .gitignore byte-for-byte, so line endings are part of the fixture."""
        _write(self.root, ".gitignore", raw, mode="wb")
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


class BlankIgnorePatternTests(TempRepoCase):
    """Regression: a blank line in a CRLF .gitignore is not protection.

    Git stores .gitignore with LF, but ``core.autocrlf=true`` checks it out with
    CRLF. Git then reads each blank line as a lone ``\\r`` and reports it as a
    match -- with an empty pattern -- for any path ending in ``/``. Every
    directory destination in this gate then looked protected on Windows while the
    same tree failed honestly on Linux, so removing a real directory rule went
    undetected on the maintainer's own machine.

    The fixture writes .gitignore byte-for-byte, so these tests read the same on
    both platforms regardless of the local autocrlf setting.
    """

    def test_a_destination_protected_only_by_a_blank_crlf_pattern_is_unprotected(self):
        for blank in (b"\r\n", b"   \r\n", b"\t\r\n"):
            with self.subTest(blank=blank):
                self.ignore_bytes(b"artifacts/\r\n" + blank + b"*.jsonl\r\n")

                problems = check_sinks(self.root, [("powerbi_report/", "--powerbi root")])

                self.assertEqual(len(problems), 1, problems)
                self.assertIn("powerbi_report/", problems[0])
                rule = check_ignore(self.root, ["powerbi_report/"])["powerbi_report/"]
                if rule is None:
                    # A git that drops the blank line entirely: no match at all.
                    self.assertIn("no ignore rule", problems[0])
                else:
                    self.assertEqual(rule[2].strip(), "", rule)
                    self.assertIn("blank pattern", problems[0])

    def test_the_same_tree_with_lf_endings_reaches_the_same_verdict(self):
        # The platform must not change the answer: unprotected either way.
        self.ignore_bytes(b"artifacts/\n\n*.jsonl\n")

        problems = check_sinks(self.root, [("powerbi_report/", "--powerbi root")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("powerbi_report/", problems[0])
        self.assertIn("no ignore rule", problems[0])

    def test_a_real_rule_in_a_crlf_gitignore_still_protects(self):
        # The fix rejects blank patterns only; a genuine CRLF rule is still a rule.
        self.ignore_bytes(b"artifacts/\r\n\r\npowerbi_report/\r\n\r\n*.jsonl\r\n")

        problems = check_sinks(
            self.root,
            [
                ("powerbi_report/", "--powerbi root"),
                ("artifacts/", "--out default folder"),
                ("anywhere/run.jsonl", "NDJSON mart"),
            ],
        )

        self.assertEqual(problems, [])

    def test_a_file_destination_was_never_covered_by_the_blank_pattern(self):
        # Why the defect hid: only directory-form destinations were made vacuous,
        # so the file-form negative tests kept passing and looked like proof.
        self.ignore_bytes(b"artifacts/\r\n\r\n")

        problems = check_sinks(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no ignore rule", problems[0])


class PlausibleDestinationTests(unittest.TestCase):
    """Regression: an English word after an output flag is prose, not a folder."""

    def test_a_prose_word_is_not_a_destination(self):
        for word in ("default", "documented", "is", "pointed", "folder", "the", "example"):
            with self.subTest(word=word):
                self.assertFalse(_is_plausible_destination(word))

    def test_every_path_shape_the_docs_use_is_a_destination(self):
        for value in (
            "./powerbi_report",
            "./lakehouse",
            "artifacts",
            "artifacts/",
            "artifacts/live-checkpoint.json",
            "lakehouse/gold/MartRunSummary/run.jsonl",
            "run.jsonl",
            "elsewhere/data/MartRunSummary.csv",
            "IsFabricReadyForIQ.pbip",
        ):
            with self.subTest(value=value):
                self.assertTrue(_is_plausible_destination(value))


class DocumentedSinkScrapeTests(TempRepoCase):
    """Regression: the scraper matched prose, including its own reason strings."""

    #: Shapes taken from this checker's own literals and comments, which is where
    #: the false positives `default/`, `documented/` and `is/` came from. Every
    #: example is assembled at runtime -- see `flag_example`.
    PROSE = (
        f'("artifacts/", "{flag_example("out", "default")} folder"),\n'
        f'("artifacts/live-checkpoint.json", "{flag_example("checkpoint", "documented")} example"),\n'
        f'("lakehouse/", "{flag_example("lakehouse", "documented")} root"),\n'
        f"# ignored wherever {flag_example('out', 'is')} pointed, not only in artifacts/.\n"
    )

    def test_a_prose_word_after_an_output_flag_is_not_a_destination(self):
        self.track("scripts/check_evidence_sinks.py", self.PROSE)

        self.assertEqual(dict(documented_sinks(self.root)), {})

    def test_a_genuine_example_in_the_same_file_is_still_caught(self):
        # No file is exempt: the fix filters by shape, not by filename.
        self.track(
            "scripts/check_evidence_sinks.py",
            self.PROSE + f"#     python assess.py {flag_example('out', './evidence_dump')}\n",
        )
        self.track(
            "README.md",
            f"python assess.py {flag_example('checkpoint', 'artifacts/live-checkpoint.json')}\n",
        )
        self.track(
            "assess.py",
            "# python assess.py "
            f"{flag_example('powerbi', './powerbi_report')} {flag_example('out', 'artifacts')}\n",
        )

        found = dict(documented_sinks(self.root))

        self.assertEqual(
            set(found),
            {"evidence_dump/", "artifacts/live-checkpoint.json", "powerbi_report/", "artifacts/"},
            found,
        )
        self.assertIn("scripts/check_evidence_sinks.py", found["evidence_dump/"])

    def test_a_genuine_unignored_example_still_fails_the_gate(self):
        # Non-vacuity of the scraper: a documented path with no rule is a finding.
        self.track(
            "README.md", f"python assess.py {flag_example('out', './tenant_dump/run.json')}\n"
        )
        self.ignore("artifacts/")

        problems = check_sinks(self.root, documented_sinks(self.root))

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("tenant_dump/run.json", problems[0])
        self.assertIn("no ignore rule", problems[0])

    def test_placeholders_and_remote_destinations_are_still_skipped(self):
        self.track(
            "docs/guide.md",
            "python assess.py "
            f"{flag_example('out', '<folder>')} {flag_example('lakehouse', '$HOME/lake')}\n",
        )
        self.track(
            "docs/more.md",
            f"python assess.py {flag_example('powerbi', 'https://example.invalid/x')}\n",
        )

        self.assertEqual(dict(documented_sinks(self.root)), {})


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

    def test_the_documented_scan_invents_no_prose_destination(self):
        # Every scraped value must look like a path, not like the next English
        # word after the flag. `default/`, `documented/` and `is/` all came from
        # reason strings in the checker itself.
        for path, why in documented_sinks(REPO_ROOT):
            with self.subTest(path=path):
                self.assertTrue(_is_plausible_destination(path), why)

    def test_no_destination_is_protected_only_by_a_blank_ignore_pattern(self):
        # If .gitignore is checked out CRLF, a blank line matches every directory
        # and this gate goes vacuous for exactly the destinations that matter.
        sinks = writer_sinks() + documented_sinks(REPO_ROOT)
        matches = check_ignore(REPO_ROOT, [path for path, _ in sinks])
        vacuous = sorted(
            path for path, rule in matches.items() if rule is not None and not rule[2].strip()
        )
        self.assertEqual(vacuous, [])

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
