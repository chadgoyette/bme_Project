import json
from pathlib import Path

import numpy as np
import pandas as pd

from training_cnn.data import (
    compute_normalisation,
    load_prepared_dir,
    train_val_split,
)


def _write_prepared(tmp_path: Path, samples: int = 6) -> Path:
    steps = 4
    features = 3
    signals = np.random.rand(samples, steps, features).astype(np.float32)
    labels = np.array([0, 1, 0, 1, 0, 1], dtype=np.int64)[:samples]
    feature_names = np.array([f"f{i}" for i in range(features)])

    np.savez_compressed(tmp_path / "sequences.npz", signals=signals, labels=labels, feature_names=feature_names)
    metadata = pd.DataFrame(
        {
            "specimen_id": [f"spec-{i//2}" for i in range(samples)],
            "sample_name": [f"sample-{i}" for i in range(samples)],
        }
    )
    metadata.to_csv(tmp_path / "index.csv", index=False)
    (tmp_path / "label_map.json").write_text(json.dumps({"A": 0, "B": 1}), encoding="utf-8")
    return tmp_path


def test_load_prepared_dir(tmp_path):
    prepared_path = _write_prepared(tmp_path)
    dataset = load_prepared_dir(prepared_path)
    assert dataset.signals.shape[0] == 6
    assert dataset.signals.shape[2] == 3
    assert dataset.feature_names == ("f0", "f1", "f2")
    assert dataset.label_map == {"A": 0, "B": 1}


def test_train_val_split_grouped(tmp_path):
    prepared_path = _write_prepared(tmp_path)
    dataset = load_prepared_dir(prepared_path)
    train_idx, val_idx = train_val_split(dataset, val_fraction=0.33, seed=42)
    assert len(train_idx) + len(val_idx) == len(dataset.labels)
    train_groups = set(dataset.metadata.iloc[train_idx]["specimen_id"])
    val_groups = set(dataset.metadata.iloc[val_idx]["specimen_id"])
    assert train_groups.isdisjoint(val_groups)


def test_compute_normalisation(tmp_path):
    prepared_path = _write_prepared(tmp_path)
    dataset = load_prepared_dir(prepared_path)
    means, stds = compute_normalisation(dataset.signals)
    assert means.shape == (dataset.signals.shape[2],)
    assert stds.shape == means.shape
