"""Synthetic-only consequence tests for the claimed-clock kernel.

No data endpoint, filesystem admission implementation, publisher attestations or
source credentials are used. Numeric times and claims are fixtures, not evidence.
"""

import unittest
from dataclasses import replace

from scripts.research.r11_d2.prospective_causal_clock import (
    ClockCalibration,
    PredeclaredSourceSet,
    SourceEvidence,
    SourcePolicy,
    SourceRequirement,
    evaluate_fixed_origin,
)


def ms(value: int) -> int:
    return value * 1_000_000


def clock() -> ClockCalibration:
    return ClockCalibration(
        boot_id="b0",
        anchor_mono_ns=0,
        anchor_utc_ns=0,
        initial_error_ns=ms(2),
        drift_ppb=0,
    )


def observation(**kwargs) -> SourceEvidence:
    values = {
        "source_id": "oi",
        "boot_id": "b0",
        "connection_id": "connection_oi",
        "epoch_id": "epoch_oi",
        "first_byte_mono_ns": ms(10009),
        "complete_mono_ns": ms(10010),
        "validated_mono_ns": ms(10012),
        "raw_ack_mono_ns": ms(10020),
        "manifest_ack_mono_ns": ms(10024),
        "admission_mono_ns": ms(10025),
        "sample_lower_utc_ns": ms(10000),
        "sample_upper_utc_ns": ms(10001),
    }
    values.update(kwargs)
    return SourceEvidence(**values)


def policy(record: SourceEvidence, **kwargs) -> SourcePolicy:
    values = {
        "source_id": record.source_id,
        "family": "OI",
        "connection_id": record.connection_id,
        "epoch_id": record.epoch_id,
        "epoch_start_mono_ns": ms(9990),
        "receiver_max_age_ns": ms(10000),
        "sample_max_age_ns": ms(10000),
        "continuity": "CONTIGUOUS",
    }
    values.update(kwargs)
    return SourcePolicy(**values)


def evaluate(
    *records,
    at: int = 10035,
    feature: int = 10030,
    feature_admit: int | None = 10030,
    origin: int = 9990,
    calibration=None,
    source_policies=None,
    required_sources=None,
):
    mapped = {r.source_id: policy(r) for r in records}
    if source_policies is not None:
        mapped = source_policies
    # Unit convenience: real callers must supply independently predeclared R(F).
    # Explicit test overrides exercise the omission and family downgrade gates.
    if required_sources is None:
        entries = tuple(SourceRequirement(name, p.family) for name, p in mapped.items())
        if not entries:
            entries = (SourceRequirement("oi", "OI"),)
        required_sources = PredeclaredSourceSet("fixture-fixed-contract", ms(origin), entries)
    return evaluate_fixed_origin(
        calibration if calibration is not None else clock(),
        records,
        mapped,
        predeclared_sources=required_sources,
        fixed_origin_utc_ns=ms(origin),
        fixed_decision_mono_ns=ms(at),
        feature_ready_mono_ns=ms(feature),
        feature_admission_mono_ns=None if feature_admit is None else ms(feature_admit),
    )


class TestClaimedClockKernel(unittest.TestCase):
    def test_p01_oracle_exact_boundary_and_early(self):
        r = evaluate(observation())
        self.assertTrue(r.claimed_timing_eligible)
        self.assertEqual(r.status, "CLAIMED_TIMING_ELIGIBLE")
        self.assertEqual(r.required_upper_utc_ns, ms(10033))
        self.assertEqual(evaluate(observation(), at=10034).status, "NO_ACTION_LATE_INFORMATION")
        self.assertFalse(hasattr(r, "eligible"))

    def test_p02_backdated_observation_received_after_decision(self):
        later = observation(
            first_byte_mono_ns=ms(10040),
            complete_mono_ns=ms(10041),
            validated_mono_ns=ms(10045),
            raw_ack_mono_ns=ms(10047),
            manifest_ack_mono_ns=ms(10049),
            admission_mono_ns=ms(10050),
        )
        self.assertEqual(
            evaluate(later, feature=10051, feature_admit=10051).status, "NO_ACTION_LATE_INFORMATION"
        )

    def test_p03_future_scheduled_funding_T_is_not_availability(self):
        r = observation(role="FUTURE_SCHEDULE_METADATA", scheduled_future_utc_ns=ms(25000))
        self.assertTrue(evaluate(r).claimed_timing_eligible)
        self.assertEqual(evaluate(replace(r, role="UNDECLARED")).status, "SOURCE_TIME_ROLE_UNKNOWN")

    def test_p04_completed_interval_end_is_required(self):
        self.assertEqual(
            evaluate(observation(role="COMPLETED_INTERVAL")).status, "SOURCE_ECONOMIC_END_UNKNOWN"
        )
        self.assertTrue(
            evaluate(
                observation(role="COMPLETED_INTERVAL", economic_end_upper_utc_ns=ms(10029))
            ).claimed_timing_eligible
        )
        self.assertEqual(
            evaluate(
                observation(role="COMPLETED_INTERVAL", economic_end_upper_utc_ns=ms(10034))
            ).status,
            "NO_ACTION_LATE_INFORMATION",
        )

    def test_p08_calibration_uncertainty_age_drift(self):
        for calibration, expected in [
            (replace(clock(), drift_ppb=-1), "CLOCK_DRIFT_UNKNOWN"),
            (replace(clock(), initial_error_ns=ms(11)), "CLOCK_ERROR_EXCESS"),
            (replace(clock(), max_age_ns=ms(61000)), "CLOCK_AGE_UNQUALIFIED"),
            (replace(clock(), anchor_mono_ns=ms(10036)), "CLOCK_CALIBRATION_EXPIRED"),
        ]:
            with self.subTest(expected=expected):
                self.assertEqual(evaluate(observation(), calibration=calibration).status, expected)

    def test_p08_boot_mismatch_blocks(self):
        self.assertEqual(
            evaluate(observation(boot_id="another_boot")).status, "SOURCE_BOOT_MISMATCH"
        )

    def test_f1_first_byte_must_be_inside_calibration(self):
        r = observation(first_byte_mono_ns=ms(9000))
        c = replace(clock(), anchor_mono_ns=ms(10000), anchor_utc_ns=ms(10000))
        result = evaluate(
            r, calibration=c, source_policies={"oi": policy(r, epoch_start_mono_ns=ms(8000))}
        )
        self.assertEqual(result.status, "CLOCK_CALIBRATION_EXPIRED")
        self.assertFalse(result.claimed_timing_eligible)
        self.assertEqual(
            evaluate(
                observation(first_byte_mono_ns=ms(10009)),
                calibration=replace(
                    clock(), anchor_mono_ns=ms(10000), anchor_utc_ns=ms(10000), max_age_ns=ms(8)
                ),
            ).status,
            "CLOCK_CALIBRATION_EXPIRED",
        )

    def test_f1_first_byte_before_explicit_epoch_start(self):
        r = observation(first_byte_mono_ns=ms(9900))
        self.assertEqual(evaluate(r).status, "SOURCE_BARRIER_OR_EPOCH_ORDER")
        self.assertEqual(
            evaluate(observation(first_byte_mono_ns=None)).status,
            "SOURCE_FULL_CLOCK_OR_ACK_MISSING",
        )

    def test_f2_same_boot_wrong_connection_or_epoch_blocks(self):
        r = observation()
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, connection_id="new_connection")}).status,
            "SOURCE_EPOCH_MISMATCH",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, epoch_id="epoch_new")}).status,
            "SOURCE_EPOCH_MISMATCH",
        )

    def test_f2_continuity_and_closed_epoch_fail(self):
        r = observation()
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, continuity="GAPPED")}).status,
            "POLICY_EPOCH_NOT_CONTIGUOUS",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, continuity="RECOVERY_REQUIRED")}).status,
            "POLICY_EPOCH_NOT_CONTIGUOUS",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, epoch_end_mono_ns=ms(10034))}).status,
            "POLICY_EPOCH_ENDED",
        )

    def test_f2_distinct_concurrent_connection_epochs_per_source_can_pass(self):
        a = observation(source_id="oi_a", connection_id="oi_conn", epoch_id="oi_epoch")
        b = observation(
            source_id="bbo_b",
            connection_id="bbo_conn",
            epoch_id="bbo_epoch",
            sample_lower_utc_ns=None,
            sample_upper_utc_ns=None,
        )
        policies = {
            "oi_a": policy(a),
            "bbo_b": policy(b, family="BBO", receiver_max_age_ns=ms(2000), sample_max_age_ns=None),
        }
        self.assertTrue(evaluate(a, b, source_policies=policies).claimed_timing_eligible)
        self.assertEqual(
            evaluate(
                a,
                b,
                source_policies={"oi_a": policy(a)},
                required_sources=PredeclaredSourceSet(
                    "fixed-ab",
                    ms(9990),
                    (SourceRequirement("oi_a", "OI"), SourceRequirement("bbo_b", "BBO")),
                ),
            ).status,
            "REQUIRED_POLICY_COVERAGE_MISMATCH",
        )

    def test_f2_mandatory_receiver_caps_cannot_be_silently_omitted(self):
        r = observation()
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, receiver_max_age_ns=None)}).status,
            "POLICY_RECEIVER_CAP_MISSING",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, receiver_max_age_ns=ms(11000))}).status,
            "POLICY_RECEIVER_CAP_TOO_WEAK",
        )
        bbo = replace(r, sample_lower_utc_ns=None, sample_upper_utc_ns=None)
        self.assertEqual(
            evaluate(
                bbo,
                at=12500,
                source_policies={
                    "oi": policy(
                        bbo, family="BBO", receiver_max_age_ns=ms(2000), sample_max_age_ns=None
                    )
                },
            ).status,
            "SOURCE_RECEIVER_STALE",
        )

    def test_p09_receiver_staleness_boundary(self):
        r = observation()
        self.assertTrue(
            evaluate(
                r, source_policies={"oi": policy(r, receiver_max_age_ns=ms(29))}
            ).claimed_timing_eligible
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, receiver_max_age_ns=ms(28))}).status,
            "SOURCE_RECEIVER_STALE",
        )

    def test_f3_OI_requires_trusted_claimed_numeric_sample_bounds(self):
        r = observation()
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, sample_max_age_ns=None)}).status,
            "POLICY_SAMPLE_CAP_MISSING",
        )
        self.assertEqual(
            evaluate(replace(r, sample_lower_utc_ns=None)).status, "SOURCE_SAMPLE_CLOCK_UNKNOWN"
        )
        self.assertEqual(
            evaluate(replace(r, sample_lower_utc_ns="fake")).status, "SOURCE_SAMPLE_CLOCK_INVALID"
        )
        self.assertEqual(
            evaluate(replace(r, sample_upper_utc_ns=ms(10020))).status,
            "SOURCE_SAMPLE_TIME_INCOHERENT",
        )
        self.assertEqual(
            evaluate(
                replace(r, sample_lower_utc_ns=ms(9000)),
                source_policies={"oi": policy(r, sample_max_age_ns=ms(100))},
            ).status,
            "SOURCE_SAMPLE_STALE",
        )

    def test_f3_type_injection_into_identity_and_policy(self):
        r = observation()
        self.assertEqual(evaluate(replace(r, source_id=123)).status, "REQUIRED_SOURCE_ID_INVALID")
        self.assertEqual(evaluate(replace(r, boot_id=123)).status, "SOURCE_BOOT_INVALID")
        self.assertEqual(
            evaluate(r, calibration=replace(clock(), boot_id=123)).status, "CLOCK_BOOT_INVALID"
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, continuity=True)}).status,
            "POLICY_EPOCH_NOT_CONTIGUOUS",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, sample_max_age_ns="fake")}).status,
            "POLICY_SAMPLE_CAP_INVALID",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, sample_max_age_ns=ms(11000))}).status,
            "POLICY_SAMPLE_CAP_TOO_WEAK",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r, receiver_max_age_ns=True)}).status,
            "POLICY_RECEIVER_CAP_MISSING",
        )

    def test_p18_ack_order_and_full_message(self):
        self.assertEqual(
            evaluate(observation(manifest_ack_mono_ns=None)).status,
            "SOURCE_FULL_CLOCK_OR_ACK_MISSING",
        )
        self.assertEqual(
            evaluate(observation(admission_mono_ns=ms(10024))).status,
            "SOURCE_BARRIER_OR_EPOCH_ORDER",
        )
        self.assertEqual(
            evaluate(observation(first_byte_mono_ns=ms(10011))).status,
            "SOURCE_BARRIER_OR_EPOCH_ORDER",
        )
        self.assertEqual(
            evaluate(observation(complete_mono_ns=None)).status, "SOURCE_FULL_CLOCK_OR_ACK_MISSING"
        )

    def test_f4_feature_level_admission_cannot_be_omitted(self):
        self.assertEqual(
            evaluate(observation(), feature_admit=None).status, "FEATURE_ADMISSION_UNKNOWN"
        )
        self.assertEqual(
            evaluate(observation(), feature_admit=10029).status, "FEATURE_ADMISSION_PRECEDES_READY"
        )
        self.assertEqual(
            evaluate(observation(admission_mono_ns=ms(10031))).status,
            "FEATURE_PRECEDES_SOURCE_ADMISSION",
        )

    def test_p21_fixed_origin_and_late_Z_keep_population(self):
        x = observation(source_id="x")
        z = observation(
            source_id="z",
            validated_mono_ns=ms(10040),
            raw_ack_mono_ns=ms(10042),
            manifest_ack_mono_ns=ms(10043),
            admission_mono_ns=ms(10044),
        )
        self.assertTrue(evaluate(x).claimed_timing_eligible)
        res = evaluate(x, z, feature=10045, feature_admit=10045, origin=9990)
        self.assertEqual(res.status, "NO_ACTION_LATE_INFORMATION")
        self.assertEqual(res.fixed_origin_utc_ns, ms(9990))

    def test_p21_no_sources_duplicate_or_early_origin_fail(self):
        self.assertEqual(evaluate().status, "REQUIRED_SOURCE_MISSING")
        self.assertEqual(evaluate(observation(), observation()).status, "DUPLICATE_SOURCE_ID")
        self.assertEqual(
            evaluate(observation(), origin=10034).status, "DECISION_PRECEDES_FIXED_ORIGIN"
        )

    def test_p21_feature_ready_and_bool_numbers_rejected(self):
        self.assertEqual(
            evaluate(observation(), feature=10011).status, "FEATURE_PRECEDES_SOURCE_ADMISSION"
        )
        self.assertEqual(
            evaluate(observation(), calibration=replace(clock(), initial_error_ns=True)).status,
            "CLOCK_ERROR_UNKNOWN",
        )

    def test_r3_f1_required_z_cannot_be_silently_omitted(self):
        x = observation(source_id="x")
        z = observation(source_id="z")
        frozen = PredeclaredSourceSet(
            "fixed-xz", ms(9990), (SourceRequirement("x", "OI"), SourceRequirement("z", "OI"))
        )
        policies = {"x": policy(x), "z": policy(z)}
        self.assertTrue(
            evaluate(
                x, z, source_policies=policies, required_sources=frozen
            ).claimed_timing_eligible
        )
        omitted = evaluate(x, source_policies=policies, required_sources=frozen)
        self.assertEqual(omitted.status, "REQUIRED_SOURCE_MISSING")
        self.assertEqual(omitted.fixed_origin_utc_ns, ms(9990))
        self.assertFalse(omitted.claimed_timing_eligible)
        self.assertEqual(
            evaluate(x, z, source_policies={"x": policy(x)}, required_sources=frozen).status,
            "REQUIRED_POLICY_COVERAGE_MISMATCH",
        )

    def test_r3_f1_reject_unregistered_extra_source(self):
        x = observation(source_id="x")
        z = observation(source_id="z")
        frozen = PredeclaredSourceSet("fixed-x", ms(9990), (SourceRequirement("x", "OI"),))
        self.assertEqual(evaluate(x, z, required_sources=frozen).status, "UNDECLARED_SOURCE")

    def test_r3_f2_family_is_not_downgradeable_by_policy(self):
        r = observation(sample_lower_utc_ns=None, sample_upper_utc_ns=None)
        contract = PredeclaredSourceSet("frozen-oi", ms(9990), (SourceRequirement("oi", "OI"),))
        downgraded = policy(r, family="DERIVED", sample_max_age_ns=None)
        self.assertEqual(
            evaluate(r, source_policies={"oi": downgraded}, required_sources=contract).status,
            "SOURCE_FAMILY_CONTRACT_MISMATCH",
        )
        self.assertEqual(
            evaluate(r, source_policies={"oi": policy(r)}, required_sources=contract).status,
            "SOURCE_SAMPLE_CLOCK_UNKNOWN",
        )

    def test_r3_contract_types_empty_duplicates_and_extra_policy(self):
        x = observation(source_id="x")
        for invalid, reason in [
            (PredeclaredSourceSet("broken", ms(9990), ()), "REQUIRED_SOURCE_SET_INVALID"),
            (
                PredeclaredSourceSet("broken", ms(9990), [SourceRequirement("x", "OI")]),
                "REQUIRED_SOURCE_SET_INVALID",
            ),
            (
                PredeclaredSourceSet(
                    "broken", ms(9990), (SourceRequirement("x", "OI"), SourceRequirement("x", "OI"))
                ),
                "REQUIRED_SOURCE_DUPLICATE",
            ),
            (
                PredeclaredSourceSet("broken", ms(9990), (SourceRequirement("x", "UNKNOWN"),)),
                "REQUIRED_SOURCE_FAMILY_INVALID",
            ),
            (
                PredeclaredSourceSet("broken", ms(9990), (SourceRequirement(123, "OI"),)),
                "REQUIRED_SOURCE_ID_INVALID",
            ),
        ]:
            with self.subTest(code=reason):
                self.assertEqual(evaluate(x, required_sources=invalid).status, reason)
        frozen = PredeclaredSourceSet("fixed-x", ms(9990), (SourceRequirement("x", "OI"),))
        self.assertEqual(
            evaluate(
                x,
                source_policies={"x": policy(x), "z": policy(observation(source_id="z"))},
                required_sources=frozen,
            ).status,
            "REQUIRED_POLICY_COVERAGE_MISMATCH",
        )

    def test_r3_claimed_contract_cannot_be_reused_at_another_origin(self):
        r = observation()
        frozen = PredeclaredSourceSet("frozen-oi", ms(9990), (SourceRequirement("oi", "OI"),))
        self.assertEqual(
            evaluate(r, origin=9991, required_sources=frozen).status,
            "REQUIRED_ORIGIN_MISMATCH",
        )

    def test_r3_f3_committed_feature_ready_must_follow_source_admission(self):
        r = observation()
        self.assertEqual(
            evaluate(r, feature=10012, feature_admit=10030).status,
            "FEATURE_PRECEDES_SOURCE_ADMISSION",
        )
        self.assertTrue(evaluate(r, feature=10025, feature_admit=10030).claimed_timing_eligible)
        self.assertEqual(
            evaluate(r, feature=10030, feature_admit=10030).required_upper_utc_ns, ms(10033)
        )


if __name__ == "__main__":
    unittest.main()
