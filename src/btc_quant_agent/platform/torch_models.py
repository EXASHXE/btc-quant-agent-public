"""Small CPU-first neural models. Architecture imports remain optional for ordinary strategies."""

from __future__ import annotations

import random

import numpy as np
import torch
from torch import nn

from .ml import ModelEvaluator


class TemporalNetwork(nn.Module):
    def __init__(self, family, features, hidden, context):
        super().__init__()
        self.family = family
        self.embedding = nn.Linear(features, hidden)
        position = torch.arange(context, dtype=torch.float32).unsqueeze(1)
        divisor = torch.exp(torch.arange(0, hidden, 2) * (-np.log(10000) / hidden))
        encoding = torch.zeros(context, hidden)
        encoding[:, 0::2] = torch.sin(position * divisor)
        encoding[:, 1::2] = torch.cos(position * divisor[: encoding[:, 1::2].shape[1]])
        self.register_buffer("positional_encoding", encoding)
        if family == "transformer":
            layer = nn.TransformerEncoderLayer(
                hidden, 2 if hidden % 2 == 0 else 1, hidden * 2, dropout=0, batch_first=True
            )
            self.temporal = nn.TransformerEncoder(layer, 1, enable_nested_tensor=False)
        elif family == "lstm":
            self.temporal = nn.LSTM(hidden, hidden, batch_first=True)
        else:
            self.temporal = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU())
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        if x.ndim == 2:
            x = x.unsqueeze(1)
        embedded = self.embedding(x) + self.positional_encoding[: x.size(1)]
        if self.family == "transformer":
            # Every query may attend only to its prefix. Inputs themselves end at decision time.
            mask = torch.triu(torch.ones(x.size(1), x.size(1), device=x.device, dtype=torch.bool), diagonal=1)
            out = self.temporal(embedded, mask=mask, is_causal=True)
        elif self.family == "lstm":
            out, _ = self.temporal(embedded)
        else:
            out = self.temporal(embedded)
        return self.head(out[:, -1]).squeeze(-1)


def make_network(family, features, hidden, context):
    return TemporalNetwork(family, features, hidden, context)


def sequences(data, x, context):
    windows = []
    sample_indices = []
    for symbol in sorted(set(data.symbols)):
        ids = np.flatnonzero(data.symbols == symbol)
        for n in range(context - 1, len(ids)):
            window = ids[n - context + 1 : n + 1]
            if not np.all(np.diff(data.times[window]) > 0):
                raise ValueError("NONCAUSAL_SEQUENCE")
            windows.append(x[window])
            sample_indices.append(ids[n])
    return np.asarray(windows, dtype=np.float32), np.asarray(sample_indices)


def train_network(config, data, split, x, mean, std, path, classification):
    random.seed(config.ml.seed)
    np.random.seed(config.ml.seed)
    torch.manual_seed(config.ml.seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    device = "cuda" if config.ml.device == "auto" and torch.cuda.is_available() else "cpu"
    windows, ids = sequences(data, x, config.ml.context)
    train = np.flatnonzero(np.isin(ids, split.train))
    val = np.flatnonzero(np.isin(ids, split.validation))
    if len(train) < 10 or len(val) < 5:
        raise ValueError("INSUFFICIENT_SEQUENCE_PARTITIONS")
    model = make_network(config.ml.family, x.shape[1], config.ml.hidden, config.ml.context).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002)
    loss_fn = nn.BCEWithLogitsLoss() if classification else nn.MSELoss()
    inputs = torch.tensor(windows, dtype=torch.float32, device=device)
    targets = torch.tensor(data.y[ids], dtype=torch.float32, device=device)
    model.train()
    losses = []
    for _ in range(config.ml.epochs):
        for offset in range(0, len(train), 32):
            batch = train[offset : offset + 32]
            optimizer.zero_grad()
            loss = loss_fn(model(inputs[batch]), targets[batch])
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        train_pred = model(inputs[train])
        val_pred = model(inputs[val])
        if classification:
            train_pred = torch.sigmoid(train_pred)
            val_pred = torch.sigmoid(val_pred)
    metrics = {
        "training": ModelEvaluator.evaluate(data.y[ids[train]], train_pred.cpu().numpy(), classification),
        "validation": ModelEvaluator.evaluate(data.y[ids[val]], val_pred.cpu().numpy(), classification),
        "losses": losses,
        "device": device,
        "causal_attention_mask": config.ml.family == "transformer",
        "sequence_context": config.ml.context,
    }
    artifact = "checkpoint.pt"
    torch.save(
        {
            "state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
            "family": config.ml.family,
            "features": x.shape[1],
            "hidden": config.ml.hidden,
            "context": config.ml.context,
            "mean": torch.tensor(mean),
            "std": torch.tensor(std),
            "schema_version": "1.0.0",
        },
        path / artifact,
    )
    actual = windows[val[:5]] * std + mean
    probe = val_pred[:5].cpu().numpy()
    return metrics, artifact, probe, actual
