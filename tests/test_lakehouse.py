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

import unittest

from fabric_iq.lakehouse import GOLD_SCHEMAS, GOLD_TABLES, gold_mart_rows
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


if __name__ == "__main__":
    unittest.main()
