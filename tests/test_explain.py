import unittest

from helpers import signal

from btc_quant_agent.explain import explain_signal


class ExplainTests(unittest.TestCase):
    def test_explanation_preserves_uncalibrated_state(self) -> None:
        result = explain_signal(signal())
        self.assertEqual(result["statistical_probability"], "not calibrated")
        self.assertTrue(result["numbers_are_immutable"])


if __name__ == "__main__":
    unittest.main()
