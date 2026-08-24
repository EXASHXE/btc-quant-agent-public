import unittest

from helpers import signal

from btc_quant_agent.notify.feishu import build_card


class NotifyTests(unittest.TestCase):
    def test_card_does_not_invent_probability(self) -> None:
        card = build_card(signal())
        content = card["card"]["elements"][0]["content"]
        self.assertIn("尚未校准", content)
        self.assertIn("EXPERIMENTAL", content)


if __name__ == "__main__":
    unittest.main()
