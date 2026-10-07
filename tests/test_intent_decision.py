import unittest

from hello_bot.routing.models import Intent, IntentDecision


class IntentDecisionTests(unittest.TestCase):
    def test_invalid_confidence_cannot_enter_routing_contract(self):
        for value in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(confidence=value), self.assertRaises(ValueError):
                IntentDecision(Intent.SUPPORT, value)

    def test_uncertain_decision_keeps_its_confidence(self):
        decision = IntentDecision(Intent.OTHER, 0.2)
        self.assertLess(decision.confidence, 0.5)
        self.assertEqual(decision.intent, Intent.OTHER)
