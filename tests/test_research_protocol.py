import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btc_quant_agent.config import AppConfig
from btc_quant_agent.research_protocol import (
    DEV_END_MS,
    DEV_START_MS,
    HOLDOUT_END_MS,
    HOLDOUT_START_MS,
    consume_holdout_gate,
    validate_research_manifest,
    write_freeze_certificate,
)


def manifest(checksum: str = "dataset") -> dict[str, object]:
    return {
        "timezone": "UTC",
        "start_ms": DEV_START_MS,
        "end_ms_exclusive": HOLDOUT_END_MS,
        "missing_count": 0,
        "duplicate_count": 0,
        "out_of_order_count": 0,
        "invalid_ohlc_count": 0,
        "negative_volume_count": 0,
        "synthetic_rows": 0,
        "checksum_sha256": checksum,
        "funding": {"missing_mark_prices": 0, "duplicate_count": 0},
    }


class ResearchProtocolTests(unittest.TestCase):
    def test_utc_development_and_holdout_are_disjoint(self) -> None:
        self.assertLess(DEV_START_MS, DEV_END_MS)
        self.assertEqual(DEV_END_MS, HOLDOUT_START_MS)
        self.assertLess(HOLDOUT_START_MS, HOLDOUT_END_MS)
        validate_research_manifest(manifest())

    def test_holdout_cannot_be_consumed_before_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            with self.assertRaisesRegex(PermissionError, "sealed"):
                consume_holdout_gate(
                    root / "missing.json",
                    config=AppConfig(),
                    dataset_manifest_path=manifest_path,
                )

    def test_matching_freeze_is_consumable_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificate_path = root / "freeze.json"
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            write_freeze_certificate(certificate_path, AppConfig(), "dataset", "abc123")
            with patch(
                "btc_quant_agent.research_protocol._tag_commit", return_value="abc123"
            ):
                consumed = consume_holdout_gate(
                    certificate_path,
                    config=AppConfig(),
                    dataset_manifest_path=manifest_path,
                )
                self.assertIsNotNone(consumed["holdout_consumed_at_ms"])
                with self.assertRaisesRegex(PermissionError, "not_consumed"):
                    consume_holdout_gate(
                        certificate_path,
                        config=AppConfig(),
                        dataset_manifest_path=manifest_path,
                    )

    def test_config_hash_mismatch_rejects_holdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificate_path = root / "freeze.json"
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            write_freeze_certificate(certificate_path, AppConfig(), "dataset", "abc123")
            payload = json.loads(certificate_path.read_text(encoding="utf-8"))
            payload["candidate_config_hash"] = "tampered"
            certificate_path.write_text(json.dumps(payload), encoding="utf-8")
            with (
                patch("btc_quant_agent.research_protocol._tag_commit", return_value="abc123"),
                self.assertRaisesRegex(PermissionError, "config_hash"),
            ):
                consume_holdout_gate(
                    certificate_path,
                    config=AppConfig(),
                    dataset_manifest_path=manifest_path,
                )


if __name__ == "__main__":
    unittest.main()
