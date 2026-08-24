import tempfile
import unittest
from pathlib import Path

from helpers import candles

from btc_quant_agent.data.csvio import read_candles, write_candles


class CsvTests(unittest.TestCase):
    def test_canonical_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            expected = candles(3, "1m", 60_000)
            write_candles(path, expected)
            self.assertEqual(read_candles(path), expected)


if __name__ == "__main__":
    unittest.main()
