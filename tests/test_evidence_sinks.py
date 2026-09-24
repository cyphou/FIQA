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
import unittest.mock

from scripts.check_evidence_sinks import (
    ALLOWED_EMAIL_DOMAINS,
    GOLD_TABLES,
    OUTPUT_FLAGS,
    SINK_ROOTS,
    SINK_SUFFIXES,
    _CALIBRATION_SUFFIX_FALLBACK,
    _FLAG_EXAMPLE,
    _GOLD_TABLES_FALLBACK,
    _calibration_sinks_fallback,
    _is_placeholder_guid,
    _is_plausible_destination,
    audit,
    calibration_sinks,
    check_ignore,
    check_sinks,
    check_tracked_not_shadowed,
    documented_sinks,
    main,
    scan_tracked_identifiers,
    tracked_files,
    writer_sinks,
)
from fabric_iq.calibration import (
    CALIBRATION_ARTIFACTS,
    CALIBRATION_SINK_ROOT,
    calibration_sinks as writer_calibration_sinks,
)
from tests.helpers import REPO_ROOT


def tenant_shaped_guid() -> str:
    """A GUID that looks like a tenant issued it, assembled so no literal exists."""
    return "-".join(["3f2b9c71", "4d2e", "4a11", "9b33", "7c5d1e2f4a6b"])


def tenant_shaped_undashed_guid() -> str:
    """The same id as a token claim carries it: 32 hex characters, no dashes."""
    return tenant_shaped_guid().replace("-", "")


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

    def test_a_rule_from_git_info_exclude_does_not_count(self):
        # .git/info/exclude protects one clone only. A teammate who runs the
        # documented command still commits the evidence.
        self.ignore("artifacts/")
        _write(self.root, ".git/info/exclude", "powerbi_report/\n")

        problems = check_sinks(self.root, [("powerbi_report/data/MartRunSummary.csv", "marts")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("not a committed .gitignore", problems[0])

    def test_an_untracked_gitignore_does_not_count(self):
        """Regression: an uncommitted rule was accepted whenever it was *named* .gitignore.

        The previous test claimed "not committed" but only ever exercised
        ``.git/info/exclude``, which is caught by its filename. A ``.gitignore``
        that git does not track is exactly as private -- it exists in one working
        tree, and a teammate's clone has no such rule -- and it passed the gate
        green while the destination was unprotected for everybody else.
        """
        self.ignore("artifacts/")  # tracked, and deliberately without *.jsonl
        self.assertEqual(
            len(check_sinks(self.root, [("elsewhere/run.jsonl", "NDJSON mart")])),
            1,
            "precondition: the tracked rules must not already cover the destination",
        )
        # Present on disk, never `git add`-ed.
        _write(self.root, "elsewhere/.gitignore", "*.jsonl\n")

        problems = check_sinks(self.root, [("elsewhere/run.jsonl", "NDJSON mart")])

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("elsewhere/.gitignore", problems[0])
        self.assertIn("not a committed .gitignore", problems[0])

    def test_the_same_nested_rule_counts_once_git_tracks_it(self):
        # Non-vacuity of the fix: the check rejects the *untracked* state, not
        # nested .gitignore files, so adding the very same file clears the gate.
        self.ignore("artifacts/")
        _write(self.root, "elsewhere/.gitignore", "*.jsonl\n")
        _git(self.root, "add", "--", "elsewhere/.gitignore")

        self.assertEqual(check_sinks(self.root, [("elsewhere/run.jsonl", "NDJSON mart")]), [])


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

    def test_every_path_shape_a_writer_destination_can_take_is_recognised(self):
        # Not only the shapes this repository happens to use today: a test that
        # enumerates the current fixture certifies the fixture, not the property.
        # `results/`, `evidence/` and `./out` are shapes the docs are *allowed* to
        # use, and every one of them must reach question 1 of the gate.
        for value in (
            "./powerbi_report",
            "./lakehouse",
            "./out",
            "artifacts",
            "artifacts/",
            "results/",
            "evidence/",
            "artifacts/live-checkpoint.json",
            "lakehouse/gold/MartRunSummary/run.jsonl",
            "run.jsonl",
            "elsewhere/data/MartRunSummary.csv",
            "IsFabricReadyForIQ.pbip",
        ):
            with self.subTest(value=value):
                self.assertTrue(_is_plausible_destination(value))

    def test_a_single_level_folder_with_a_trailing_slash_is_a_destination(self):
        """Regression: the separator was tested *after* it had been stripped off.

        ``"/" in candidate.strip("/")`` removes the one character that proves the
        value is a path, so a single-level output folder written with a trailing
        slash was discarded as prose and never checked against the ignore rules at
        all. Only a folder that happened to be listed in SINK_ROOTS, or one nested
        deeply enough to keep an interior slash, survived -- which is why the
        defect looked like it worked.
        """
        for folder in ("results", "evidence", "tenant_dump", "out"):
            with self.subTest(folder=folder):
                self.assertNotIn(folder, SINK_ROOTS, "a bare root would pass for another reason")
                self.assertFalse(_is_plausible_destination(folder))
                self.assertTrue(_is_plausible_destination(folder + "/"))
                self.assertTrue(_is_plausible_destination(folder + "\\"))

    def test_a_value_made_only_of_separators_names_no_destination(self):
        for value in ("/", "//", "\\", ""):
            with self.subTest(value=value):
                self.assertFalse(_is_plausible_destination(value))


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

    def test_a_documented_single_level_folder_reaches_the_ignore_check(self):
        """Regression (end to end): a single-level folder was dropped before question 1.

        The scrape and the verdict are both asserted. A scraper that finds the
        folder while the check ignores it is the same fail-open wearing a
        different hat, so proving only that the value is collected is not enough.
        """
        self.track("README.md", f"python assess.py {flag_example('out', 'results/')}\n")
        self.ignore("artifacts/")

        found = dict(documented_sinks(self.root))

        self.assertIn("results/", found, found)
        problems = check_sinks(self.root, documented_sinks(self.root))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("results/", problems[0])
        self.assertIn("no ignore rule", problems[0])

    def test_a_documented_single_level_folder_that_is_ignored_passes(self):
        # Non-vacuity: the finding above is about the missing rule, not the shape.
        self.track("README.md", f"python assess.py {flag_example('out', 'results/')}\n")
        self.ignore("artifacts/", "results/")

        self.assertEqual(check_sinks(self.root, documented_sinks(self.root)), [])

    def test_a_documented_folder_is_scraped_out_of_a_utf16_document(self):
        # A document git tracks is a document that instructs somebody, whatever
        # encoding an editor saved it in.
        self.track(
            "docs/guide.md",
            f"python assess.py {flag_example('out', 'results/')}\n".encode("utf-16"),
            mode="wb",
        )

        self.assertIn("results/", dict(documented_sinks(self.root)))


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

    def test_a_binary_file_yields_nothing_and_does_not_crash_the_scan(self):
        self.track("assets/logo.bin", b"\xff\xfe\x00\x01binary", mode="wb")

        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_an_identifier_in_a_binary_file_is_still_reported(self):
        # Byte-wise scanning is the point: an ASCII identifier does not stop being
        # tenant evidence because it sits in a file with an unreadable header.
        self.track(
            "assets/logo.bin",
            b"\xff\xfe\x00\x01" + tenant_shaped_guid().encode("ascii") + b"\x00\x01",
            mode="wb",
        )

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn(tenant_shaped_guid(), problems[0])


class NonUtf8ContentScanTests(TempRepoCase):
    """Regression: 'not UTF-8' was treated as 'nothing textual to leak'.

    The scan opened every tracked file as UTF-8 and swallowed ``UnicodeDecodeError``
    with a comment claiming the file was binary. A UTF-16 document is neither
    binary nor unreadable: the same GUID that was reported in a UTF-8 file went
    unreported in its UTF-16 twin, and the failure mode was silence.

    A BOM-less UTF-16 file is the sharper case -- it decodes as UTF-8 *without*
    raising, because NUL is a valid UTF-8 byte, so a fallback triggered only by a
    decode failure would still have missed it.
    """

    ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "cp1252")

    def test_every_text_encoding_leaks_exactly_like_its_utf8_twin(self):
        for encoding in self.ENCODINGS:
            with self.subTest(encoding=encoding):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
                    _git(root, "init", "-q")
                    _write(
                        root,
                        "docs/example.md",
                        f"first line\ntenant {tenant_shaped_guid()}\n".encode(encoding),
                        mode="wb",
                    )
                    _git(root, "add", "--", "docs/example.md")

                    problems = scan_tracked_identifiers(root)

                    self.assertEqual(len(problems), 1, f"{encoding}: {problems}")
                    self.assertIn(tenant_shaped_guid(), problems[0])
                    # The line number must still point at the leak, not at line 1.
                    self.assertTrue(problems[0].startswith("docs/example.md:2"), problems[0])

    def test_a_utf16_document_of_placeholders_still_passes(self):
        # Non-vacuity: the fallback reports identifiers, not encodings.
        self.track(
            "docs/example.md",
            "id 00000000-0000-0000-0000-000000000001\nowner person@example.invalid\n".encode(
                "utf-16"
            ),
            mode="wb",
        )

        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_a_tracked_file_that_cannot_be_read_is_reported_not_skipped(self):
        # An unscanned file that reports nothing looks exactly like a clean one.
        self.track("docs/example.md", "# synthetic\n")
        os.remove(os.path.join(self.root, "docs", "example.md"))

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("docs/example.md", problems[0])
        self.assertIn("never scanned", problems[0])


class UndashedGuidTests(TempRepoCase):
    """A tenant id copied from a token claim carries no dashes."""

    def test_an_undashed_tenant_id_is_reported(self):
        self.track("docs/example.md", f"tid {tenant_shaped_undashed_guid()}\n")

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn(tenant_shaped_undashed_guid(), problems[0])
        self.assertIn("undashed", problems[0])

    def test_an_undashed_placeholder_and_a_longer_hex_run_still_pass(self):
        self.track(
            "docs/example.md",
            f"placeholder {'0' * 31}1\n"
            # A 40-character commit sha must not be mistaken for a 32-hex id.
            f"commit {'ab' * 20}\n",
        )

        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_a_dashed_guid_is_reported_once_not_twice(self):
        self.track("docs/example.md", f"tenant {tenant_shaped_guid()}\n")

        self.assertEqual(len(scan_tracked_identifiers(self.root)), 1)


class NonAsciiTrackedPathTests(TempRepoCase):
    """Regression: an octal-quoted path was invisible to every check.

    Under the default ``core.quotePath`` git renders ``docs/café.md`` as the
    literal ``"docs/caf\\303\\251.md"``. That string opens nothing (the OSError was
    swallowed) and matches no ignore rule, so the file was silently exempt from
    both the identifier scan and the shadowing check. Each test below pairs the
    non-ASCII file with an ASCII twin, so a fix that broke *both* cannot pass.
    """

    NON_ASCII = "docs/caf\u00e9.md"

    def test_a_non_ascii_path_round_trips_verbatim(self):
        self.track(self.NON_ASCII, "# synthetic\n")

        files = tracked_files(self.root)

        self.assertIn(self.NON_ASCII, files, files)
        self.assertFalse([path for path in files if path.startswith('"')], files)

    def test_an_identifier_in_a_non_ascii_path_is_reported(self):
        self.track("docs/ascii.md", f"tenant {tenant_shaped_guid()}\n")
        self.track(self.NON_ASCII, f"tenant {tenant_shaped_guid()}\n")

        problems = scan_tracked_identifiers(self.root)

        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any(p.startswith("docs/ascii.md:") for p in problems), problems)
        self.assertTrue(any(p.startswith(f"{self.NON_ASCII}:") for p in problems), problems)

    def test_a_shadowed_non_ascii_file_is_reported(self):
        self.track("docs/ascii.md", "# synthetic\n")
        self.track(self.NON_ASCII, "# synthetic\n")
        self.ignore("*.md")

        problems = check_tracked_not_shadowed(self.root)

        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any(p.startswith(self.NON_ASCII) for p in problems), problems)

    def test_check_ignore_keys_a_non_ascii_path_by_the_name_it_was_given(self):
        self.ignore("*.md")

        matches = check_ignore(self.root, [self.NON_ASCII, "docs/ascii.md"])

        self.assertEqual(set(matches), {self.NON_ASCII, "docs/ascii.md"})
        for path, rule in matches.items():
            with self.subTest(path=path):
                self.assertIsNotNone(rule)
                self.assertEqual(rule[2], "*.md")

    def test_an_unshadowed_non_ascii_file_reports_nothing(self):
        # Non-vacuity: the file is now visible, not reported unconditionally.
        self.track(self.NON_ASCII, "# synthetic\n")
        self.ignore("artifacts/")

        self.assertEqual(check_tracked_not_shadowed(self.root), [])
        self.assertEqual(scan_tracked_identifiers(self.root), [])

    def test_a_path_holding_a_control_character_survives_the_parse(self):
        """``-z`` is the other half of the quoting fix, and it needs its own proof.

        ``core.quotePath=false`` stops git C-quoting *non-ASCII* names, but git
        quotes a control character in a path unconditionally, whatever that setting
        says. Only NUL-separated output is immune. Windows refuses such a filename
        outright, so this test skips there and carries its weight on Linux CI.
        """
        weird = "docs/we\nird.md"
        try:
            _write(self.root, weird, f"tenant {tenant_shaped_guid()}\n")
            _git(self.root, "add", "--", weird)
        except (OSError, AssertionError) as error:
            self.skipTest(f"this filesystem refuses a control character in a name: {error}")

        self.assertIn(weird, tracked_files(self.root))
        problems = scan_tracked_identifiers(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith(f"{weird}:"), problems[0])

    def test_tracked_files_reads_git_output_as_nul_separated_records(self):
        """The same guarantee without a filesystem that has to cooperate.

        Line-splitting ``git ls-files`` cannot represent a path that contains a
        newline: the entry breaks into two names, neither of which exists, and both
        the shadowing check and the identifier scan then look at nothing. The stub
        returns exactly what ``ls-files -z`` documents, so the parse contract is
        asserted on every platform.
        """
        record = "docs/we\nird.md"
        stdout = "\0".join([".gitignore", record, "docs/plain.md"]) + "\0"
        completed = subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")

        with unittest.mock.patch(
            "scripts.check_evidence_sinks._git", return_value=completed
        ) as fake:
            files = tracked_files(self.root)

        self.assertEqual(files, [".gitignore", record, "docs/plain.md"])
        self.assertIn("-z", fake.call_args.args, fake.call_args)


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


class CalibrationSinkTests(TempRepoCase):
    """The calibration key is the most identifying artifact this tool produces.

    It carries real object and workspace names, their ids, and the tool's own
    score, status, confidence and coverage for each. Its protection must be
    *asserted* by the gate, not inherited from whichever root it happens to sit
    under today: a changed default path or a sixth output file would otherwise
    leave the privacy claim resting on a coincidence.
    """

    RUN = "20260101T000000Z"

    def test_the_gate_enumerates_every_destination_the_writer_reports(self):
        # The wiring itself. If writer_sinks stops extending with the writer's own
        # enumeration, every other test in this class still passes while the gate
        # checks nothing about calibration at all.
        enumerated = {path for path, _ in writer_sinks()}
        for path, why in writer_calibration_sinks(self.RUN):
            with self.subTest(path=path):
                self.assertIn(path, enumerated, why)

    def test_every_calibration_output_is_checked_at_the_default_and_a_relocated_root(self):
        # Truth comes from the writer's own table of artifacts, so adding a file
        # there without covering it here fails rather than passing silently.
        enumerated = {path for path, _ in writer_sinks()}
        for suffix, why in CALIBRATION_ARTIFACTS:
            with self.subTest(suffix=suffix):
                self.assertIn(f"{CALIBRATION_SINK_ROOT}/{self.RUN}{suffix}", enumerated, why)
                self.assertIn(f"elsewhere/{self.RUN}{suffix}", enumerated, why)

    def test_the_instruction_sheet_is_covered_although_md_is_not_a_sink_suffix(self):
        # Deliberate design note, made executable. `.md` stays out of SINK_SUFFIXES
        # (that tuple only decides whether a bare scraped *word* is a file or
        # prose, and `.md` is what every document here is written in). The
        # instruction sheet is covered by name instead, at both roots.
        self.assertNotIn(".md", SINK_SUFFIXES)
        sheet = [
            (path, why)
            for path, why in writer_sinks()
            if path.endswith("_calibration_instructions.md")
        ]
        self.assertEqual(len(sheet), 2, sheet)
        self.assertEqual(check_sinks(REPO_ROOT, sheet), [])

    def test_the_fallback_enumeration_still_matches_the_writer(self):
        # The fallback is what runs when fabric_iq cannot be imported. Untested, it
        # would quietly check fewer destinations while still reporting "clean".
        self.assertEqual(
            [path for path, _ in _calibration_sinks_fallback(self.RUN)],
            [path for path, _ in writer_calibration_sinks(self.RUN)],
        )
        self.assertEqual(
            [suffix for suffix, _ in CALIBRATION_ARTIFACTS], list(_CALIBRATION_SUFFIX_FALLBACK)
        )
        self.assertEqual(tuple(_GOLD_TABLES_FALLBACK), tuple(GOLD_TABLES))

    def test_a_relocated_calibration_output_without_a_basename_rule_is_reported(self):
        # Ignoring the default root only is not protection: the flag can point the
        # writers anywhere, which is why .gitignore carries basename patterns. Drop
        # them and every relocated destination must be reported.
        self.ignore("artifacts/")

        problems = check_sinks(self.root, writer_calibration_sinks(self.RUN))

        reported = {problem.split(" - ")[0] for problem in problems}
        for suffix, _ in CALIBRATION_ARTIFACTS:
            with self.subTest(suffix=suffix):
                self.assertIn(f"elsewhere/{self.RUN}{suffix}", reported)
                self.assertNotIn(f"{CALIBRATION_SINK_ROOT}/{self.RUN}{suffix}", reported)

    def test_a_changed_default_root_fails_the_gate(self):
        # The scenario that motivated the wiring: a future edit moves the default
        # calibration folder out from under the one ignore rule covering it today.
        with unittest.mock.patch("fabric_iq.calibration.CALIBRATION_SINK_ROOT", "calibration_out"):
            problems = check_sinks(REPO_ROOT, writer_sinks())

        self.assertTrue(problems, "a root no ignore rule covers must be reported")
        self.assertTrue(
            any(problem.startswith("calibration_out/") for problem in problems), problems
        )

    def test_a_newly_added_calibration_output_with_no_rule_fails_the_gate(self):
        # A sixth output file, added later, whose extension no rule covers.
        orphan = f"elsewhere/{self.RUN}_calibration_rater_notes.txt"

        def with_a_new_output(run_id=self.RUN):
            return writer_calibration_sinks(run_id) + [(orphan, "free-text notes on named objects")]

        with unittest.mock.patch(
            "scripts.check_evidence_sinks.calibration_sinks", with_a_new_output
        ):
            problems = check_sinks(REPO_ROOT, writer_sinks())

        self.assertTrue(any(problem.startswith(orphan) for problem in problems), problems)

    def test_the_gate_exits_nonzero_when_a_calibration_destination_is_unprotected(self):
        # End to end, through main(), because the exit code is what CI reads.
        with unittest.mock.patch("fabric_iq.calibration.CALIBRATION_SINK_ROOT", "calibration_out"):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([])

        self.assertEqual(code, 1)
        self.assertIn("calibration_out/", buffer.getvalue())


class CalibrationFlagScrapeTests(unittest.TestCase):
    """How the calibration flags are read out of tracked documentation."""

    def test_the_documented_calibration_folder_is_scraped_and_ignored(self):
        found = dict(documented_sinks(REPO_ROOT))
        self.assertIn(f"{CALIBRATION_SINK_ROOT}/", found)
        self.assertEqual(check_sinks(REPO_ROOT, sorted(found.items())), [])

    def test_the_analyse_flag_is_read_whole_not_truncated(self):
        # Alternation order matters: read as the shorter flag, the value would be
        # the remainder of the option name and every documented key path would
        # silently drop out of the scan.
        value = "artifacts/calibration/run_calibration_key.json"
        text = flag_example("calibration-analyse", value)

        matches = _FLAG_EXAMPLE.findall(text)

        self.assertEqual(matches, [("calibration-analyse", value)])

    def test_the_analyse_example_reaches_the_ignore_check(self):
        # The agreement report and disagreement CSV are written beside the key this
        # flag names, so a documented key path is a documented output folder.
        found = dict(documented_sinks(REPO_ROOT))
        analysed = [path for path, why in found.items() if "calibration-analyse" in why]
        self.assertTrue(analysed, sorted(found.items()))
        self.assertEqual(check_sinks(REPO_ROOT, [(path, "analyse") for path in analysed]), [])

    def test_a_labels_flag_is_not_treated_as_an_output(self):
        # Rater-typed worksheets are inputs this tool never writes. Scanning them
        # would demand an ignore rule for a file the practitioner owns.
        self.assertNotIn("calibration-labels", OUTPUT_FLAGS)
        example = flag_example("calibration-labels", "a=labels.csv")
        self.assertEqual(_FLAG_EXAMPLE.findall(example), [])


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
