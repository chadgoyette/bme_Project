import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from training.train import build_pipeline
from training.utils import prepare_dataset


def make_features_df() -> pd.DataFrame:
    rows = []
    for specimen in ("A", "B"):
        for i in range(4):
            rows.append(
                {
                    "specimen_id": specimen,
                    "run_id": f"{specimen}-run",
                    "window_start_ms": i * 1000,
                    "window_end_ms": i * 1000 + 999,
                    "quality_class": "clean",
                    "freshness_label": "fresh" if specimen == "A" else "aged",
                    "meat_type": "beef",
                    "gas_mean": 1.0 + i,
                    "gas_std": 0.1,
                    "gas_min": 0.5,
                    "gas_max": 1.5,
                    "gas_slope_per_s": 0.01,
                    "gas_mean_abs_diff": 0.05,
                    "gas_early_late_ratio": 1.0,
                    "gas_delta_mean": 0.2,
                    "gas_delta_std": 0.1,
                    "gas_delta_min": 0.0,
                    "gas_delta_max": 0.4,
                    "gas_delta_slope_per_s": 0.01,
                    "gas_delta_mean_abs_diff": 0.05,
                    "gas_delta_early_late_ratio": 1.0,
                    "temperature_mean": 21.0,
                    "temperature_range": 1.0,
                    "humidity_mean": 40.0,
                    "humidity_range": 2.0,
                    "age_days": 0 if specimen == "A" else 3,
                }
            )
    return pd.DataFrame(rows)


def test_prepare_dataset_returns_expected_columns():
    df = make_features_df()
    X, y, groups, cat_cols, num_cols, label_map = prepare_dataset(df, group_col="specimen_id")
    assert "quality_class" in X.columns
    assert "gas_mean" in X.columns
    assert len(y) == df.shape[0]
    assert set(label_map.keys()) == {"aged", "fresh"}
    assert cat_cols == ["quality_class", "meat_type"]
    assert "age_days" in num_cols


def test_group_kfold_separates_groups():
    df = make_features_df()
    X, y, groups, cat_cols, num_cols, _ = prepare_dataset(df, group_col="specimen_id")
    gkf = GroupKFold(n_splits=2)
    for train_idx, test_idx in gkf.split(X, y, groups=groups):
        train_groups = set(groups[train_idx])
        test_groups = set(groups[test_idx])
        # train and test groups should not intersect
        assert train_groups.isdisjoint(test_groups)


def test_pipeline_trains_on_synthetic_data():
    df = make_features_df()
    X, y, groups, cat_cols, num_cols, _ = prepare_dataset(df, group_col="specimen_id")
    pipeline = build_pipeline("rf", cat_cols, num_cols, seed=123)
    pipeline.fit(X, y)
    probs = pipeline.predict_proba(X)
    assert probs.shape == (X.shape[0], len(np.unique(y)))
