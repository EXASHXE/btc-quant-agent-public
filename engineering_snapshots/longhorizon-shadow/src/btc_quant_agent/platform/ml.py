"""Offline model workbench. Chronological event splits, purging and train-only scaling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .backtest import build_pipeline
from .config import PlatformConfig
from .core import ModelManifest, fingerprint, primitive
from .data import SyntheticProvider, dataset_hash, histories

CLASSIFICATION_TARGETS = {
    "direction",
    "volatility_expansion",
    "breakout_continuation",
    "stop_first",
    "fill_probability",
}
TARGETS = CLASSIFICATION_TARGETS | {"future_return", "drawdown", "recovery"}


@dataclass(frozen=True)
class TargetDefinition:
    name: str
    horizon: int
    tie_policy: str = "stop first; ambiguous OHLC sequencing is adverse"


@dataclass
class FeatureDataset:
    x: np.ndarray
    y: np.ndarray
    times: np.ndarray
    label_ends: np.ndarray
    symbols: np.ndarray
    feature_names: tuple[str, ...]
    dataset_hash: str
    target: str


class DatasetBuilder:
    def build(self, config: PlatformConfig, events=None) -> FeatureDataset:
        if config.ml.target not in TARGETS:
            raise ValueError(f"unknown learning target: {config.ml.target}")
        events = events if events is not None else SyntheticProvider().events(config)
        if any(e.provenance.exposure != "SYNTHETIC" for e in events):
            raise ValueError("ONLY_SYNTHETIC_TRAINING_AUTHORIZED")
        pipeline, indices = build_pipeline(events, config)
        h = config.ml.horizon
        if config.ml.target == "volatility_expansion" and h < 2:
            raise ValueError("volatility_expansion requires at least two future returns")
        records = []
        for symbol, group in histories(events).items():
            df = pipeline.frames[symbol]
            for i in range(40, len(group) - h):
                event = group[i]
                index = indices[symbol].get(event.candle.close_time_ms, -1)
                if index < 0:
                    continue
                values = [
                    pipeline.result(symbol, id, index, event.decision_ts).value for id in config.ml.features
                ]
                if any(v is None for v in values):
                    continue
                future = group[i + 1 : i + h + 1]
                if any(e.reason(10**15) for e in future):
                    continue
                close = event.candle.close
                ret = future[-1].candle.close / close - 1
                target = config.ml.target
                if target == "direction":
                    label = float(ret > 0)
                elif target == "future_return":
                    label = ret
                elif target == "drawdown":
                    label = min(0.0, min(e.candle.low / close - 1 for e in future))
                elif target == "recovery":
                    label = (future[-1].candle.close - min(e.candle.low for e in future)) / close
                elif target == "volatility_expansion":
                    past = (
                        df.close.iloc[max(0, index - h) : index + 1]
                        .pct_change(fill_method=None)
                        .dropna()
                        .std()
                    )
                    forward = np.std(np.diff(np.log([close] + [e.candle.close for e in future])), ddof=1)
                    label = float(forward > past)
                elif target == "breakout_continuation":
                    boundary = float(df.high.iloc[max(0, index - 14) : index].max())
                    label = float(close > boundary and ret > 0)
                elif target == "fill_probability":
                    limit = close * 0.998
                    label = float(
                        any(
                            e.quote is not None
                            and not e.quote.reason(e.spec, e.decision_ts)
                            and float(e.quote.ask) < limit
                            and e.quote.ask_quantity is not None
                            and e.quote.ask_quantity > 0
                            for e in future
                        )
                    )
                else:
                    atr = pipeline.result(symbol, "ATR", index, event.decision_ts).value
                    if atr is None:
                        continue
                    label = 0.0
                    resolved = False
                    for e in future:
                        if e.candle.low <= close - atr:
                            label = 1.0
                            resolved = True
                            break
                        if e.candle.high >= close + atr:
                            resolved = True
                            break
                    if not resolved:
                        continue  # Censored: neither barrier hit; never label it target-first.
                label_end = max(max(e.provenance.available_ts, e.candle.available_at_ms) for e in future)
                records.append((event.decision_ts, symbol, values, label, label_end))
        records.sort(key=lambda r: (r[0], r[1]))
        if len(records) < 40:
            raise ValueError("INSUFFICIENT_CAUSAL_TRAINING_SAMPLES")
        return FeatureDataset(
            np.asarray([r[2] for r in records], dtype=np.float64),
            np.asarray([r[3] for r in records], dtype=np.float64),
            np.asarray([r[0] for r in records]),
            np.asarray([r[4] for r in records]),
            np.asarray([r[1] for r in records]),
            tuple(config.ml.features),
            dataset_hash(events),
            config.ml.target,
        )


@dataclass(frozen=True)
class TrainValidationSplit:
    train: np.ndarray
    validation: np.ndarray
    split_ts: int
    purged: int
    embargo_ms: int

    @classmethod
    def chronological(cls, data: FeatureDataset, embargo_ms: int, fraction: float = 0.7):
        unique = np.unique(data.times)
        split = int(unique[int(len(unique) * fraction)])
        train = np.flatnonzero((data.times < split) & (data.label_ends < split - embargo_ms))
        validation = np.flatnonzero(data.times >= split)
        if len(train) < 20 or len(validation) < 10:
            raise ValueError("INSUFFICIENT_PURGED_PARTITIONS")
        return cls(
            train,
            validation,
            split,
            int(((data.times < split) & ~np.isin(np.arange(len(data.times)), train)).sum()),
            embargo_ms,
        )


class ModelTrainer(Protocol):
    def fit(self, x, y): ...
    def predict(self, x): ...


class ExperimentalTrainer(Protocol):
    """Extension point for RL/self-supervision/other architectures. No JEV or SSA claim."""

    def train(self, data: FeatureDataset, split: TrainValidationSplit, seed: int) -> dict: ...


class LinearBaseline:
    """NumPy logistic/ridge fallback; portable and deterministic without sklearn."""

    def __init__(self, classification=True):
        self.classification = classification

    def fit(self, x, y):
        design = np.column_stack([np.ones(len(x)), x])
        if self.classification:
            self.weights = np.zeros(design.shape[1])
            for _ in range(200):
                pred = 1 / (1 + np.exp(-np.clip(design @ self.weights, -30, 30)))
                self.weights -= 0.1 * (design.T @ (pred - y) / len(y) + 0.001 * self.weights)
        else:
            self.weights = np.linalg.solve(design.T @ design + 0.01 * np.eye(design.shape[1]), design.T @ y)
        return self

    def predict(self, x):
        pred = np.column_stack([np.ones(len(x)), x]) @ self.weights
        return 1 / (1 + np.exp(-np.clip(pred, -30, 30))) if self.classification else pred


def make_model(family: str, classification: bool, seed: int):
    if family in ("logistic", "linear", "numpy"):
        return LinearBaseline(classification), "numpy_logistic" if classification else "numpy_ridge"
    try:
        from sklearn.ensemble import (
            RandomForestClassifier,
            RandomForestRegressor,
            GradientBoostingClassifier,
            GradientBoostingRegressor,
        )
        from sklearn.svm import SVC, SVR
    except ImportError as exc:
        raise RuntimeError(f"{family} unavailable: install the ml extra") from exc
    if family == "random_forest":
        model = (RandomForestClassifier if classification else RandomForestRegressor)(
            n_estimators=20, max_depth=4, random_state=seed, n_jobs=1
        )
    elif family == "svm":
        model = SVC(C=1, probability=False, random_state=seed) if classification else SVR(C=1)
    elif family in ("tree", "gradient_boosting"):
        model = (GradientBoostingClassifier if classification else GradientBoostingRegressor)(
            n_estimators=20, max_depth=2, random_state=seed
        )
    elif family == "lightgbm":
        try:
            from lightgbm import LGBMClassifier, LGBMRegressor
        except ImportError as exc:
            raise RuntimeError("lightgbm unavailable: install lightgbm explicitly") from exc
        model = (LGBMClassifier if classification else LGBMRegressor)(
            n_estimators=15,
            max_depth=3,
            num_leaves=7,
            random_state=seed,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
    else:
        raise ValueError(f"unsupported model family {family}")
    return model, family


def predictions(model, x, classification):
    if isinstance(model, LinearBaseline):
        return np.asarray(model.predict(x))
    if classification and hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x))[:, 1]
    if classification and hasattr(model, "decision_function"):
        return 1 / (1 + np.exp(-np.clip(model.decision_function(x), -30, 30)))
    return np.asarray(model.predict(x))


class ModelEvaluator:
    @staticmethod
    def evaluate(y, pred, classification):
        if classification:
            bins = []
            for lower in np.arange(0, 1, 0.2):
                mask = (pred >= lower) & (pred < lower + 0.2)
                if mask.any():
                    bins.append(
                        {
                            "count": int(mask.sum()),
                            "mean_score": float(pred[mask].mean()),
                            "outcome_rate": float(y[mask].mean()),
                        }
                    )
            return {
                "accuracy": float(((pred >= 0.5) == y).mean()),
                "brier_score": float(np.mean((pred - y) ** 2)),
                "calibration_bins": bins,
                "calibrated_probability": False,
                "samples": len(y),
            }
        return {
            "mse": float(np.mean((pred - y) ** 2)),
            "mae": float(np.mean(np.abs(pred - y))),
            "samples": len(y),
        }


class Calibration:
    """Optional Platt map; callers must provide a separate chronological calibration partition."""

    def fit(self, scores, labels):
        self.model = LinearBaseline(True).fit(np.asarray(scores).reshape(-1, 1), labels)
        return self

    def transform(self, scores):
        return self.model.predict(np.asarray(scores).reshape(-1, 1))


class PredictionAdapter:
    """Research rank score only; never grants execution or calibrated-profit authority."""

    def rank(self, symbols, scores):
        return [
            {
                "symbol": symbol,
                "model_score": float(score),
                "role": "RESEARCH_RANK_ONLY",
                "calibrated_probability": False,
            }
            for symbol, score in sorted(zip(symbols, scores), key=lambda x: (-x[1], x[0]))
        ]


class ModelRegistry:
    def __init__(self, path):
        self.path = Path(path)

    def list(self):
        return [json.loads(f.read_text()) for f in sorted(self.path.glob("*/manifest.json"))]


class InferenceService:
    def __init__(self, path):
        path = Path(path)
        self.manifest = json.loads((path / "manifest.json").read_text())
        artifact = path / self.manifest["artifact"]
        if fingerprint(artifact.read_bytes().hex()) != self.manifest["artifact_sha256"]:
            raise ValueError("MODEL_ARTIFACT_HASH_MISMATCH")
        if artifact.suffix == ".npz":
            with np.load(artifact, allow_pickle=False) as state:
                self.mean = state["mean"]
                self.std = state["std"]
                self.model = LinearBaseline(bool(state["classification"].item()))
                self.model.weights = state["weights"]
        elif artifact.suffix == ".pt":
            import torch
            from .torch_models import make_network

            state = torch.load(artifact, map_location="cpu", weights_only=True)
            self.mean = state["mean"].numpy()
            self.std = state["std"].numpy()
            self.model = make_network(state["family"], state["features"], state["hidden"], state["context"])
            self.model.load_state_dict(state["state_dict"])
            self.model.eval()
        else:
            # Only locally generated trusted model artifacts; never load untrusted pickle files.
            import pickle

            with artifact.open("rb") as stream:
                state = pickle.load(stream)
            self.model = state["model"]
            self.mean = state["mean"]
            self.std = state["std"]

    def predict(self, x):
        normalized = (np.asarray(x) - self.mean) / self.std
        classification = self.manifest["target"] in CLASSIFICATION_TARGETS
        if self.manifest["family"] in ("mlp", "lstm", "transformer"):
            import torch

            with torch.no_grad():
                tensor = torch.tensor(normalized, dtype=torch.float32)
                pred = self.model(tensor)
                if classification:
                    pred = torch.sigmoid(pred)
            return pred.numpy().reshape(-1)
        return predictions(self.model, normalized, classification)


def train(config: PlatformConfig, output, events=None):
    from .reporting import source_identity

    data = DatasetBuilder().build(config, events)
    split = TrainValidationSplit.chronological(data, config.ml.embargo * config.interval_seconds * 1000)
    classification = config.ml.target in CLASSIFICATION_TARGETS
    if classification and len(np.unique(data.y[split.train])) < 2:
        raise ValueError("TRAINING_TARGET_HAS_ONE_CLASS")
    family = config.ml.family
    mean = data.x[split.train].mean(axis=0)
    std = data.x[split.train].std(axis=0)
    std = np.where(std > 1e-12, std, 1)
    x = (data.x - mean) / std
    source_hash = source_identity()
    model_id = fingerprint([config.hash, data.dataset_hash, family, source_hash])
    path = Path(output) / model_id
    path.mkdir(parents=True, exist_ok=True)
    if family in ("mlp", "lstm", "transformer"):
        from .torch_models import train_network

        metrics, artifact, probe, actual_x = train_network(
            config, data, split, x, mean, std, path, classification
        )
    else:
        model, implementation = make_model(family, classification, config.ml.seed)
        model.fit(x[split.train], data.y[split.train])
        metrics = {
            "training": ModelEvaluator.evaluate(
                data.y[split.train], predictions(model, x[split.train], classification), classification
            ),
            "validation": ModelEvaluator.evaluate(
                data.y[split.validation],
                predictions(model, x[split.validation], classification),
                classification,
            ),
            "implementation": implementation,
        }
        artifact = "model.npz" if isinstance(model, LinearBaseline) else "model.pkl"
        if isinstance(model, LinearBaseline):
            np.savez(
                path / artifact, weights=model.weights, mean=mean, std=std, classification=classification
            )
        else:
            import pickle

            with (path / artifact).open("wb") as stream:
                pickle.dump({"model": model, "mean": mean, "std": std}, stream)
        actual_x = data.x[split.validation[:5]]
        probe = predictions(model, (actual_x - mean) / std, classification)
    manifest = ModelManifest(
        model_id,
        family,
        "1.0.0",
        data.feature_names,
        data.target,
        config.ml.seed,
        data.dataset_hash,
        (int(data.times[split.train].min()), int(data.times[split.train].max())),
        (int(data.times[split.validation].min()), int(data.times[split.validation].max())),
        metrics,
        artifact,
        (
            "Synthetic-only engineering fit; no economic Alpha or OOS market evidence.",
            "Model scores are uncalibrated; normalization fitted on training partition only.",
            "Chronological split purges labels overlapping validation and applies configured embargo.",
        ),
    )
    raw = primitive(manifest)
    raw.update(
        exposure="SYNTHETIC",
        source_hash=source_hash,
        config_hash=config.hash,
        hyperparameters=config.ml.model_dump(mode="json"),
        split={
            "purged_samples": split.purged,
            "embargo_ms": split.embargo_ms,
            "max_train_label_end": int(data.label_ends[split.train].max()),
            "validation_start": int(data.times[split.validation].min()),
        },
        input_availability_rule="completed feature dependencies available <= sample decision_ts",
        artifact_sha256=fingerprint((path / artifact).read_bytes().hex()),
    )
    (path / "manifest.json").write_text(json.dumps(raw, indent=2, allow_nan=False) + "\n")
    reloaded = InferenceService(path).predict(actual_x)
    if not np.allclose(probe, reloaded, rtol=1e-5, atol=1e-6):
        raise ValueError("INFERENCE_RELOAD_MISMATCH")
    raw["reload_max_error"] = float(np.max(np.abs(probe - reloaded)))
    (path / "manifest.json").write_text(json.dumps(raw, indent=2, allow_nan=False) + "\n")
    (path / "research_predictions.json").write_text(
        json.dumps(
            PredictionAdapter().rank(data.symbols[split.validation[: len(reloaded)]], reloaded), indent=2
        )
        + "\n"
    )
    return raw
