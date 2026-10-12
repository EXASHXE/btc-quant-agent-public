"""Baseline observation probes, not a passing application engineering gate."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/audits/r3_codex_causal_audit_r1/review.py"
SPEC = spec_from_file_location("independent_accounting_review", SCRIPT)
review = module_from_spec(SPEC)
SPEC.loader.exec_module(review)


@pytest.fixture(scope="module")
def pinned_sources(tmp_path_factory):
    stage = tmp_path_factory.mktemp("synthetic-pinned-accounting")
    review.prepare_sources(stage)
    return stage


@pytest.mark.parametrize("case", review.CASES, ids=review.CASES)
def test_frozen_baseline_observation(pinned_sources, case):
    result = review.run_case(pinned_sources, case)
    assert result["input_label"] == "SYNTHETIC_ONLY"
    review.assert_baseline_observation(result)
