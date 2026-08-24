import hashlib
import hmac
import unittest
import urllib.parse
from unittest.mock import patch

from btc_quant_agent.execution.binance_signed import BinanceSignedClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"code":200}'


class BinanceSignedTests(unittest.TestCase):
    @patch(
        "btc_quant_agent.execution.binance_signed.urllib.request.urlopen",
        return_value=FakeResponse(),
    )
    @patch("btc_quant_agent.execution.binance_signed.time.time", return_value=1.0)
    def test_post_body_is_hmac_signed(self, _time, urlopen) -> None:
        client = BinanceSignedClient("https://example.test", "key", "secret")
        client.change_leverage("BTCUSDT", 5)
        request = urlopen.call_args.args[0]
        query = urllib.parse.urlencode(
            {
                "symbol": "BTCUSDT",
                "leverage": 5,
                "timestamp": 1000,
                "recvWindow": 5000,
            }
        )
        signature = hmac.new(b"secret", query.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(request.full_url, "https://example.test/fapi/v1/leverage")
        self.assertEqual(request.data.decode(), f"{query}&signature={signature}")
        self.assertEqual(request.get_method(), "POST")

    @patch(
        "btc_quant_agent.execution.binance_signed.urllib.request.urlopen",
        return_value=FakeResponse(),
    )
    @patch("btc_quant_agent.execution.binance_signed.time.time", return_value=1.0)
    def test_algo_cancel_uses_algo_id_without_symbol(self, _time, urlopen) -> None:
        client = BinanceSignedClient("https://example.test", "key", "secret")
        client.cancel_protective_order("BTCUSDT", "123")
        request = urlopen.call_args.args[0]
        self.assertIn("algoId=123", request.full_url)
        self.assertNotIn("symbol=", request.full_url)
        self.assertEqual(request.get_method(), "DELETE")


if __name__ == "__main__":
    unittest.main()
