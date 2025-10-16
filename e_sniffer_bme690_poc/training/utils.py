from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

ID_COLUMNS = {"specimen_id", "run_id", "window_start_ms", "window_end_ms", "freshness_label"}
CATEGORICAL_CANDIDATES = ("quality_class", "meat_type")


def load_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Features parquet not found: {path}")
    return pd.read_parquet(path)


def prepare_dataset(df: pd.DataFrame, group_col: str) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, List[str], List[str], Dict[str, int]]:
    if "freshness_label" not in df.columns:
        raise ValueError("features parquet must include 'freshness_label' column")
    y_labels = df["freshness_label"].astype(str).to_numpy()
    groups = df[group_col].astype(str).to_numpy()

    categorical_cols = [col for col in CATEGORICAL_CANDIDATES if col in df.columns]
    numeric_cols = [
        col
        for col in df.columns
        if col not in ID_COLUMNS
        and col not in categorical_cols
        and pd.api.types.is_numeric_dtype(df[col])
    ]

    X = df[categorical_cols + numeric_cols].copy()

    encoder = LabelEncoder()
    y_encoded = encoder.fit_transform(y_labels)
    label_map = {label: int(idx) for idx, label in enumerate(encoder.classes_)}

    return X, y_encoded, groups, categorical_cols, numeric_cols, label_map


def update_split_metadata(prepared_root: Path, payload: Dict[str, object]) -> None:
    target = prepared_root / "split.json"
    if target.exists():
        with target.open("r", encoding="utf-8") as fp:
            existing = json.load(fp)
    else:
        existing = {}
    existing.update(payload)
    target.write_text(json.dumps(existing, indent=2), encoding="utf-8")
