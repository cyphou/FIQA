"""Executable self-assessment gate for the FIQA semantic model and report."""

import unittest

from fabric_iq.collectors.offline import OfflineCollector
from fabric_iq.models import ObjectType, ReadinessStatus
from fabric_iq.scoring import assess
from tests.helpers import FIQA_SELF_ASSESSMENT


class TestFiqaSelfAssessmentGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collection = OfflineCollector(FIQA_SELF_ASSESSMENT).collect().validate()
        cls.assessment_run = assess(collection.inventory, run_id="self_assessment_gate")

    def _only_card(self, object_type):
        cards = self.assessment_run.by_type(object_type)
        self.assertEqual(len(cards), 1)
        return cards[0]

    def test_readiness_semantic_model_passes_its_own_gate(self):
        card = self._only_card(ObjectType.SEMANTIC_MODEL)

        self.assertEqual(card.status, ReadinessStatus.READY)
        self.assertTrue(card.eligible)
        self.assertGreaterEqual(card.score, 85.0)
        self.assertGreaterEqual(card.confidence, 0.90)
        self.assertGreaterEqual(card.coverage, 0.90)
        self.assertFalse(card.blocking_findings)

    def test_readiness_report_passes_its_own_gate(self):
        card = self._only_card(ObjectType.REPORT)

        self.assertEqual(card.status, ReadinessStatus.READY)
        self.assertTrue(card.eligible)
        self.assertGreaterEqual(card.score, 85.0)
        self.assertGreaterEqual(card.confidence, 0.90)
        self.assertGreaterEqual(card.coverage, 0.90)
        self.assertFalse(card.blocking_findings)


if __name__ == "__main__":
    unittest.main()
