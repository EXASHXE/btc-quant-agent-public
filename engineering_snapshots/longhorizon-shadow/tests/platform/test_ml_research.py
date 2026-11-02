import json

import numpy as np
import pytest

from btc_quant_agent.platform.config import PlatformConfig, StrategyConfig
from btc_quant_agent.platform.ml import (
    CLASSIFICATION_TARGETS,
    DatasetBuilder,
    InferenceService,
    ModelRegistry,
    TrainValidationSplit,
    train,
)
from btc_quant_agent.platform.portfolio_research import run as portfolio_run, target_weights
from btc_quant_agent.platform.research import search, walk_forward


@pytest.mark.parametrize(
    "family",
    [
        "logistic",
        "linear",
        "random_forest",
        "svm",
        "gradient_boosting",
        "lightgbm",
        "mlp",
        "lstm",
        "transformer",
    ],
)
def test_cpu_model_training_checkpoint_and_research_adapter(family, tmp_path):
    c = PlatformConfig(bars=120)
    c = c.model_copy(
        update={
            "ml": c.ml.model_copy(
                update={"family": family, "target": "future_return" if family == "linear" else "direction"}
            )
        }
    )
    manifest = train(c, tmp_path)
    assert manifest["reload_max_error"] < 1e-5
    assert manifest["split"]["max_train_label_end"] < manifest["split"]["validation_start"]
    path = tmp_path / manifest["model_id"]
    assert (path / manifest["artifact"]).exists()
    ranks = json.loads((path / "research_predictions.json").read_text())
    assert all(r["role"] == "RESEARCH_RANK_ONLY" and not r["calibrated_probability"] for r in ranks)
    if family in ("mlp", "lstm", "transformer"):
        assert manifest["metrics"]["device"] == "cpu"
    assert ModelRegistry(tmp_path).list()[0]["dataset_hash"] == manifest["dataset_hash"]


@pytest.mark.parametrize("target", sorted(CLASSIFICATION_TARGETS | {"future_return", "drawdown", "recovery"}))
def test_all_learning_targets_have_purged_time_splits(target):
    c = PlatformConfig(bars=110)
    c = c.model_copy(update={"ml": c.ml.model_copy(update={"target": target})})
    data = DatasetBuilder().build(c)
    split = TrainValidationSplit.chronological(data, 120000)
    assert data.label_ends[split.train].max() + 120000 < data.times[split.validation].min()
    assert np.isfinite(data.x).all() and np.isfinite(data.y).all()
    assert not set(data.times[split.train]) & set(data.times[split.validation])


def test_scaler_is_fitted_on_training_only_and_artifact_integrity(tmp_path):
    c = PlatformConfig(bars=120)
    data = DatasetBuilder().build(c)
    split = TrainValidationSplit.chronological(data, 120000)
    manifest = train(c, tmp_path)
    artifact = tmp_path / manifest["model_id"] / manifest["artifact"]
    with np.load(artifact) as state:
        np.testing.assert_allclose(state["mean"], data.x[split.train].mean(axis=0))
    artifact.write_bytes(artifact.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        InferenceService(artifact.parent)


def test_transformer_mask_prevents_future_attention():
    import torch
    from btc_quant_agent.platform.torch_models import make_network

    torch.manual_seed(7)
    model = make_network("transformer", 4, 8, 12).eval()
    x = torch.randn(2, 12, 4)
    y = x.clone()
    y[:, 6:] = 1000
    mask = torch.triu(torch.ones(12, 12, dtype=torch.bool), diagonal=1)
    with torch.no_grad():
        a = model.temporal(model.embedding(x) + model.positional_encoding, mask=mask, is_causal=True)
        b = model.temporal(model.embedding(y) + model.positional_encoding, mask=mask, is_causal=True)
    torch.testing.assert_close(a[:, :6], b[:, :6], rtol=1e-5, atol=1e-5)


def test_unresolved_barrier_labels_remain_censored():
    from btc_quant_agent.platform.demos import market

    c = PlatformConfig(bars=100, universe=["BTCUSDT"])
    c = c.model_copy(update={"ml": c.ml.model_copy(update={"target": "stop_first"})})
    events = [market(100, i) for i in range(1, 101)]
    with pytest.raises(ValueError, match="INSUFFICIENT_CAUSAL_TRAINING_SAMPLES"):
        DatasetBuilder().build(c, events)


@pytest.mark.parametrize(
    "id",
    ["funding_carry", "pair_trading", "grid", "volatility_target", "rebalance", "relative_strength_rotation"],
)
def test_research_portfolios_account_for_distinct_legs_and_costs(id):
    c = PlatformConfig(bars=120, strategies=[StrategyConfig(id=id)])
    result = portfolio_run(c)
    assert result["status"] == "RESEARCH_ONLY"
    assert np.isfinite(result["metrics"]["modeled_net_pnl"])
    assert result["metrics"]["fees"] >= 0
    if id == "funding_carry":
        assert (
            result["leg_sources"][0]["market"] == "SPOT" and result["leg_sources"][1]["market"] == "PERPETUAL"
        )
        assert len(result["open_legs_at_cutoff"]) == 2
        assert result["metrics"]["leg_fills"] >= 2


def test_walk_forward_and_search_account_for_trials():
    c = PlatformConfig(bars=100)
    folds = walk_forward(c)
    assert all(f["train_max_label_end"] < f["validation_start"] for f in folds)
    result = search(c, {"entry.region_bps": [30, 50]}, "synthetic-source", method="random", max_trials=1)
    assert result["configurations_evaluated"] == 1 and "PRIMARY" in result["warnings"][0]


def test_allocation_weights_are_finite_and_collateralized():
    prices = np.array([[100 + i, 200 + i / 2] for i in range(30)])
    weights = target_weights("volatility_target", prices)
    assert np.isfinite(weights).all() and abs(weights).sum() <= 1 + 1e-10
