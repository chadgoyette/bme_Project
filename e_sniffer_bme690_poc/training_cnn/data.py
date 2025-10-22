from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupShuffleSplit
from torch.utils.data import Dataset


@dataclass
class PreparedDataset:
    signals: np.ndarray
    labels: np.ndarray
    feature_names: Tuple[str, ...]
    label_map: Dict[str, int]
    metadata: pd.DataFrame


def load_prepared_dir(prepared_dir: Path) -> PreparedDataset:
    sequences_path = prepared_dir / "sequences.npz"
    index_path = prepared_dir / "index.csv"
    label_map_path = prepared_dir / "label_map.json"

    if not sequences_path.exists():
        raise FileNotFoundError(f"Missing sequences.npz at {sequences_path}")
    npz = np.load(sequences_path)
    signals = npz["signals"]
    labels = npz["labels"]
    feature_names = tuple(npz["feature_names"].astype(str).tolist())

    if not index_path.exists():
        raise FileNotFoundError(f"Missing index.csv at {index_path}")
    metadata = pd.read_csv(index_path)

    if len(metadata) != signals.shape[0]:
        raise ValueError(
            f"Metadata rows ({len(metadata)}) do not match signals ({signals.shape[0]})."
        )

    if not label_map_path.exists():
        raise FileNotFoundError(f"Missing label_map.json at {label_map_path}")
    label_map: Dict[str, int] = pd.read_json(label_map_path, typ="series").to_dict()

    return PreparedDataset(
        signals=signals,
        labels=labels,
        feature_names=feature_names,
        label_map=label_map,
        metadata=metadata,
    )


def train_val_split(
    dataset: PreparedDataset,
    val_fraction: float,
    seed: int,
) -> Tuple[np.ndarray, np.ndarray]:
    if not 0.0 < val_fraction < 1.0:
        raise ValueError("val_fraction must be in (0, 1).")

    groups = dataset.metadata.get("specimen_id")
    if groups is None:
        groups = dataset.metadata.get("sample_name")
    if groups is None:
        groups = pd.Series(range(len(dataset.labels)))

    splitter = GroupShuffleSplit(n_splits=1, test_size=val_fraction, random_state=seed)
    train_idx, val_idx = next(splitter.split(dataset.signals, dataset.labels, groups=groups))
    return train_idx, val_idx


class SequenceDataset(Dataset[Tuple[torch.Tensor, torch.Tensor]]):
    def __init__(
        self,
        signals: np.ndarray,
        labels: np.ndarray,
        feature_means: np.ndarray,
        feature_stds: np.ndarray,
    ) -> None:
        self._signals = signals.astype(np.float32)
        self._labels = labels.astype(np.int64)
        self._feature_means = feature_means.astype(np.float32)
        self._feature_stds = np.where(feature_stds == 0.0, 1.0, feature_stds).astype(np.float32)

    def __len__(self) -> int:
        return self._signals.shape[0]

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        window = self._signals[idx]
        norm = (window - self._feature_means) / self._feature_stds
        tensor = torch.from_numpy(norm).permute(1, 0)  # (features, steps)
        label = torch.tensor(self._labels[idx], dtype=torch.int64)
        return tensor, label


def compute_normalisation(signals: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    feature_means = signals.mean(axis=(0, 1))
    feature_stds = signals.std(axis=(0, 1))
    return feature_means, feature_stds
