from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor missing in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor missing in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


QUAL = "src/btc_quant_agent/economic/qualification.py"
REG = "src/btc_quant_agent/research_contract/registry.py"
TEST = "tests/test_v041_p6_metrics_benchmarks_qualification.py"

replace_once(
    QUAL,
    "from .execution_model import ExecutionModel, ExecutionResult\n",
    "from .acceptance_verifier import (\n"
    "    bind_runtime_market_data,\n"
    "    validate_runtime_dataset_binding,\n"
    "    verify_formal_accounting,\n"
    ")\n"
    "from .execution_model import ExecutionModel, ExecutionResult\n",
)
replace_once(QUAL, 'P6_RESULT_SCHEMA_VERSION = "1.0.0"', 'P6_RESULT_SCHEMA_VERSION = "1.1.0"')
replace_once(
    QUAL,
    '        object.__setattr__(self, "product_scope", scope)\n        if not self.benchmark_vehicle.strip():\n            raise ValueError("benchmark_vehicle is required")\n',
    '        object.__setattr__(self, "product_scope", scope)\n'
    '        if len(scope) != 1:\n'
    '            raise ValueError("formal P6 comparison supports exactly one product")\n'
    '        if self.benchmark_vehicle != f"{scope[0]}_LINEAR_PERPETUAL":\n'
    '            raise ValueError("benchmark_vehicle must match the sole product scope")\n',
)
replace_once(
    QUAL,
    "    return EconomicRunResult(identity=identity, accounting=FrozenDict(summary.to_dict()))\n",
    "    accounting = bind_runtime_market_data(summary.to_dict(), candles)\n"
    "    accounting[\"formal_run_identity\"] = identity.to_dict()\n"
    "    verify_formal_accounting(\n"
    "        accounting,\n"
    "        product=protocol.product_scope[0],\n"
    "        initial_cash=comparison.initial_capital,\n"
    "        interval_start_ms=comparison.data_interval.start_ms,\n"
    "        interval_end_ms=comparison.data_interval.end_ms,\n"
    "        terminal_policy=comparison.terminal_policy,\n"
    "        metrics_contract=comparison.metrics_contract,\n"
    "    )\n"
    "    return EconomicRunResult(identity=identity, accounting=FrozenDict(accounting))\n",
)
replace_once(
    QUAL,
    '    if not candles:\n        raise ValueError("formal run requires non-empty candles")\n    if len({candle.symbol for candle in candles}) != 1:\n',
    '    if not candles:\n        raise ValueError("formal run requires non-empty candles")\n'
    '    validate_runtime_dataset_binding(\n'
    '        dataset_evidence, candles, protocol.product_scope[0]\n'
    '    )\n'
    '    if len({candle.symbol for candle in candles}) != 1:\n',
)
replace_all(
    QUAL,
    "accounting=FrozenDict(summary.to_dict()),",
    "accounting=FrozenDict(bind_runtime_market_data(summary.to_dict(), candles)),",
)

replace_once(
    REG,
    '        if (\n            dataset_reference.content_sha256\n            != run_identity.get("dataset_content_sha256")\n            or dataset_evidence_id != data_interval.get("dataset_evidence_id")\n            or dataset_reference.content_sha256\n            != data_interval.get("dataset_content_sha256")\n        ):\n            raise EvidenceValidationError("dataset identity/hash binding mismatch")\n',
    '        if (\n            dataset_reference.content_sha256\n            != run_identity.get("dataset_content_sha256")\n            or dataset_evidence_id != data_interval.get("dataset_evidence_id")\n            or dataset_reference.content_sha256\n            != data_interval.get("dataset_content_sha256")\n        ):\n            raise EvidenceValidationError("dataset identity/hash binding mismatch")\n'
    '        try:\n'
    '            from ..economic.acceptance_verifier import (\n'
    '                validate_persisted_qualification_semantics,\n'
    '            )\n'
    '            validate_persisted_qualification_semantics(semantic, dataset_reference)\n'
    '        except (KeyError, TypeError, ValueError) as exc:\n'
    '            raise EvidenceValidationError(\n'
    '                f"formal P6 semantic replay failed: {exc}"\n'
    '            ) from exc\n',
)

replace_once(
    TEST,
    '                    "open_time_ms": item.open_time_ms,\n                    "close_time_ms": item.close_time_ms,\n',
    '                    "symbol": item.symbol,\n                    "interval": item.interval,\n                    "open_time_ms": item.open_time_ms,\n                    "close_time_ms": item.close_time_ms,\n',
)
replace_once(
    TEST,
    '                    "volume": item.volume,\n',
    '                    "volume": item.volume,\n                    "quote_volume": item.quote_volume,\n',
)
replace_once(
    TEST,
    "from btc_quant_agent.economic.portfolio import Portfolio\n",
    "from btc_quant_agent.economic.acceptance_verifier import (\n"
    "    validate_persisted_qualification_semantics,\n"
    ")\n"
    "from btc_quant_agent.economic.portfolio import Portfolio\n",
)

append = r'''


def test_acceptance_repair_rejects_runtime_dataset_substitution(tmp_path: Path) -> None:
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    comparison = _comparison(dataset, candles, engine)
    protocol = _protocol(comparison, engine)
    forged = list(candles)
    forged[3] = replace(
        forged[3],
        close=forged[3].close + 0.25,
        high=forged[3].high + 0.25,
        volume=forged[3].volume + 1.0,
    )
    with pytest.raises(ValueError, match="runtime candle payload"):
        execute_bound_run(
            protocol=protocol,
            comparison=comparison,
            dataset_evidence=dataset,
            engine=engine,
            candles=tuple(forged),
            signals=(),
        )


def test_acceptance_repair_rejects_runtime_instrument_substitution(tmp_path: Path) -> None:
    candles = _candles()
    engine = _zero_cost_engine()
    dataset = _dataset_evidence(tmp_path, candles)
    comparison = _comparison(dataset, candles, engine)
    protocol = _protocol(comparison, engine)
    forged = tuple(replace(item, symbol="ETHUSDT") for item in candles)
    with pytest.raises(ValueError, match="instrument"):
        execute_bound_run(
            protocol=protocol,
            comparison=comparison,
            dataset_evidence=dataset,
            engine=engine,
            candles=forged,
            signals=(),
        )


def test_acceptance_repair_runtime_binding_is_deterministic(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    first = artifacts["run"]
    second = execute_bound_run(
        protocol=artifacts["protocol"],
        comparison=artifacts["comparison"],
        dataset_evidence=artifacts["dataset"],
        engine=artifacts["engine"],
        candles=artifacts["candles"],
        signals=(
            InformationSignal(
                signal_id="P6_CANDIDATE_ENTRY",
                experiment_id=artifacts["protocol"].experiment_revision_id,
                timestamp_ms=artifacts["candles"][0].open_time_ms,
                direction=1,
                strength=1.0,
            ),
        ),
    )
    assert first.result_id == second.result_id
    assert first.accounting["formal_runtime_market_data_sha256"] == second.accounting[
        "formal_runtime_market_data_sha256"
    ]


def test_acceptance_repair_rejects_semantically_forged_run_gate_and_random(tmp_path: Path) -> None:
    artifacts = _formal_artifacts(tmp_path)
    semantic = json.loads(canonical_json(artifacts["qualification"].semantic_payload()))
    candidate = semantic["run_result"]["semantic_payload"]["accounting"]

    forged_run = json.loads(canonical_json(semantic))
    forged_run_candidate = forged_run["run_result"]["semantic_payload"]["accounting"]
    forged_run_candidate["turnover_usdt"] += 10_000.0
    with pytest.raises(ValueError, match="replay"):
        validate_persisted_qualification_semantics(forged_run, artifacts["dataset"])

    forged_gate = json.loads(canonical_json(semantic))
    forged_gate["gates"][0]["observed_value"] = candidate["net_return_pct"] + 1.0
    forged_gate["gates"][0]["passed"] = True
    forged_gate["verdict"] = "QUALIFIED"
    with pytest.raises(ValueError, match="qualification gates"):
        validate_persisted_qualification_semantics(forged_gate, artifacts["dataset"])

    forged_random = json.loads(canonical_json(semantic))
    random_record = forged_random["benchmark_suite"]["random"]
    assert random_record is not None
    random_record["trials"][0]["matching_diagnostics"]["trial_entry_count"] += 1
    random_record["trials"][0]["comparable"] = True
    random_record["comparable"] = True
    with pytest.raises(ValueError, match="matching diagnostics"):
        validate_persisted_qualification_semantics(forged_random, artifacts["dataset"])
'''
with Path(TEST).open("a", encoding="utf-8") as handle:
    handle.write(append)

Path("tools/apply_v041e_acceptance_patch.py").unlink()
Path(".github/workflows/p6_acceptance_patch.yml").unlink()
