from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .data import (
    PreparedDataset,
    SequenceDataset,
    compute_normalisation,
    load_prepared_dir,
    train_val_split,
)
from .model import SequenceCNN

LOGGER = logging.getLogger("training_cnn")


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train 1D CNN on prepared BME690 sequences.")
    parser.add_argument(
        "--prepared-dir",
        type=Path,
        required=True,
        help="Directory that contains sequences.npz, index.csv, label_map.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Directory to write model checkpoints and metrics.",
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=5, help="Epochs to wait for val improvement before stopping.")
    return parser.parse_args(argv)


def prepare_datasets(
    prepared: PreparedDataset,
    val_fraction: float,
    seed: int,
) -> Tuple[SequenceDataset, SequenceDataset, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    train_idx, val_idx = train_val_split(prepared, val_fraction, seed=seed)
    train_signals = prepared.signals[train_idx]
    val_signals = prepared.signals[val_idx]
    train_labels = prepared.labels[train_idx]
    val_labels = prepared.labels[val_idx]

    feature_means, feature_stds = compute_normalisation(train_signals)

    train_ds = SequenceDataset(train_signals, train_labels, feature_means, feature_stds)
    val_ds = SequenceDataset(val_signals, val_labels, feature_means, feature_stds)
    return train_ds, val_ds, feature_means, feature_stds, train_idx, val_idx


def accuracy_from_logits(logits: torch.Tensor, labels: torch.Tensor) -> float:
    preds = logits.argmax(dim=1)
    return (preds == labels).float().mean().item()


def train_epoch(
    model: SequenceCNN,
    loader: DataLoader[Tuple[torch.Tensor, torch.Tensor]],
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> Tuple[float, float]:
    model.train()
    running_loss = 0.0
    running_acc = 0.0
    batches = 0
    for batch in loader:
        signals, labels = batch
        signals = signals.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        logits = model(signals)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        running_loss += loss.item()
        running_acc += accuracy_from_logits(logits.detach(), labels)
        batches += 1
    if batches == 0:
        return 0.0, 0.0
    return running_loss / batches, running_acc / batches


@torch.no_grad()
def evaluate_epoch(
    model: SequenceCNN,
    loader: DataLoader[Tuple[torch.Tensor, torch.Tensor]],
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    model.eval()
    running_loss = 0.0
    running_acc = 0.0
    batches = 0
    for signals, labels in loader:
        signals = signals.to(device)
        labels = labels.to(device)
        logits = model(signals)
        loss = criterion(logits, labels)
        running_loss += loss.item()
        running_acc += accuracy_from_logits(logits, labels)
        batches += 1
    if batches == 0:
        return 0.0, 0.0
    return running_loss / batches, running_acc / batches


def plot_history(out_path: Path, history: Dict[str, List[float]]) -> None:
    epochs = range(1, len(history["train_loss"]) + 1)
    fig, ax1 = plt.subplots(figsize=(6, 4))
    ax1.plot(epochs, history["train_loss"], label="Train loss")
    ax1.plot(epochs, history["val_loss"], label="Val loss")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Loss")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.plot(epochs, history["train_acc"], label="Train acc", color="#2ca02c")
    ax2.plot(epochs, history["val_acc"], label="Val acc", color="#ff7f0e")
    ax2.set_ylabel("Accuracy")
    ax2.set_ylim(0.0, 1.05)
    ax2.legend(loc="lower right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main(argv: List[str] | None = None) -> int:
    ns = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    LOGGER.info("Loading prepared dataset from %s", ns.prepared_dir)
    prepared = load_prepared_dir(ns.prepared_dir)
    out_dir: Path = ns.out
    out_dir.mkdir(parents=True, exist_ok=True)

    train_ds, val_ds, feature_means, feature_stds, train_idx, val_idx = prepare_datasets(
        prepared,
        val_fraction=ns.val_fraction,
        seed=ns.seed,
    )

    train_loader = DataLoader(train_ds, batch_size=ns.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=ns.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    LOGGER.info("Using device: %s", device)
    model = SequenceCNN(input_channels=train_ds[0][0].shape[0], num_classes=len(prepared.label_map)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=ns.learning_rate, weight_decay=ns.weight_decay)

    history: Dict[str, List[float]] = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best_val_loss = float("inf")
    best_state = None
    best_epoch = 0
    patience_counter = 0

    torch.manual_seed(ns.seed)
    np.random.seed(ns.seed)

    for epoch in range(1, ns.epochs + 1):
        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate_epoch(model, val_loader, criterion, device)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)

        LOGGER.info(
            "Epoch %s/%s train_loss=%.4f val_loss=%.4f train_acc=%.3f val_acc=%.3f",
            epoch,
            ns.epochs,
            train_loss,
            val_loss,
            train_acc,
            val_acc,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = model.state_dict()
            best_epoch = epoch
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= ns.patience:
                LOGGER.info("Early stopping at epoch %s (no improvement for %s epochs).", epoch, ns.patience)
                break

    if best_state is None:
        best_state = model.state_dict()

    model_path = out_dir / "model.pt"
    torch.save(
        {
            "state_dict": best_state,
            "feature_means": feature_means.astype(float).tolist(),
            "feature_stds": feature_stds.astype(float).tolist(),
            "feature_names": list(prepared.feature_names),
            "label_map": prepared.label_map,
            "config": {
                "epochs": ns.epochs,
                "batch_size": ns.batch_size,
                "learning_rate": ns.learning_rate,
                "weight_decay": ns.weight_decay,
                "val_fraction": ns.val_fraction,
                "seed": ns.seed,
                "best_epoch": best_epoch,
            },
        },
        model_path,
    )
    LOGGER.info("Saved model to %s", model_path)

    metrics = {
        "epochs_ran": len(history["train_loss"]),
        "best_epoch": best_epoch,
        "history": history,
        "best_val_loss": best_val_loss,
        "best_val_acc": history["val_acc"][best_epoch - 1] if best_epoch > 0 else history["val_acc"][-1],
        "train_indices": train_idx.tolist(),
        "val_indices": val_idx.tolist(),
        "label_map": prepared.label_map,
        "device": str(device),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    plot_history(out_dir / "training_curves.png", history)
    LOGGER.info("Wrote training artefacts to %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
