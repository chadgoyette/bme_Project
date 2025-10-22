import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from training_cnn import train as train_cli


def _create_prepared(tmp_path: Path) -> Path:
    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir()
    steps = 5
    features = 3
    samples = 10
    rng = np.random.default_rng(123)
    signals = rng.normal(size=(samples, steps, features)).astype(np.float32)
    labels = np.array([0, 1] * (samples // 2), dtype=np.int64)
    feature_names = np.array([f"f{i}" for i in range(features)])
    np.savez_compressed(prepared_dir / "sequences.npz", signals=signals, labels=labels, feature_names=feature_names)
    metadata = pd.DataFrame(
        {
            "specimen_id": [f"spec-{i//2}" for i in range(samples)],
            "sample_name": [f"sample-{i}" for i in range(samples)],
        }
    )
    metadata.to_csv(prepared_dir / "index.csv", index=False)
    (prepared_dir / "label_map.json").write_text(json.dumps({"A": 0, "B": 1}), encoding="utf-8")
    return prepared_dir


def test_train_main_produces_artifacts(tmp_path, monkeypatch):
    prepared_dir = _create_prepared(tmp_path)
    out_dir = tmp_path / "model_out"
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    args = [
        "--prepared-dir",
        str(prepared_dir),
        "--out",
        str(out_dir),
        "--epochs",
        "3",
        "--batch-size",
        "4",
        "--val-fraction",
        "0.3",
        "--patience",
        "2",
    ]
    exit_code = train_cli.main(args)
    assert exit_code == 0
    assert (out_dir / "model.pt").exists()
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "training_curves.png").exists()
