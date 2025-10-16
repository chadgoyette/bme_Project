from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .plots import save_confusion_matrix, save_feature_importances
from .utils import load_features, prepare_dataset, update_split_metadata

LOGGER = logging.getLogger("training")


def parse_args(args: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train meat freshness classifiers.")
    parser.add_argument("--in", dest="input_path", type=Path, required=True, help="Path to features.parquet")
    parser.add_argument("--out", dest="output_dir", type=Path, required=True, help="Directory for trained model.")
    parser.add_argument("--group-col", type=str, default="specimen_id", help="Grouping column for CV.")
    parser.add_argument("--model", choices=["logreg", "rf", "gbt"], default="rf", help="Model type.")
    parser.add_argument("--cv-folds", type=int, default=5, help="Number of GroupKFold splits.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args(args)


def build_preprocess(categorical_cols: List[str], numeric_cols: List[str], model_name: str) -> ColumnTransformer:
    transformers = []
    if categorical_cols:
        transformers.append(
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical_cols,
            )
        )
    if numeric_cols:
        if model_name == "logreg":
            transformers.append(("num", StandardScaler(), numeric_cols))
        else:
            transformers.append(("num", "passthrough", numeric_cols))
    if not transformers:
        raise ValueError("No feature columns available for training.")
    return ColumnTransformer(transformers=transformers, sparse_threshold=0.0)


def build_pipeline(model_name: str, categorical_cols: List[str], numeric_cols: List[str], seed: int) -> Pipeline:
    preprocess = build_preprocess(categorical_cols, numeric_cols, model_name)
    if model_name == "logreg":
        estimator = LogisticRegression(max_iter=1000, solver="lbfgs")
    elif model_name == "rf":
        estimator = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=-1)
    elif model_name == "gbt":
        estimator = GradientBoostingClassifier(random_state=seed)
    else:  # pragma: no cover - guarded by argparse choices
        raise ValueError(f"Unsupported model type: {model_name}")
    return Pipeline(
        steps=[
            ("preprocess", preprocess),
            ("model", estimator),
        ]
    )


def run_training(ns: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    features_path: Path = ns.input_path
    output_dir: Path = ns.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    features_df = load_features(features_path)
    X, y, groups, categorical_cols, numeric_cols, label_map = prepare_dataset(features_df, group_col=ns.group_col)

    if len(np.unique(groups)) < ns.cv_folds:
        raise ValueError("Number of groups is smaller than cv-folds.")

    gkf = GroupKFold(n_splits=ns.cv_folds)

    y_true: List[int] = []
    y_pred: List[int] = []
    fold_metrics = []

    for fold_idx, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups=groups), start=1):
        LOGGER.info("Fold %s/%s", fold_idx, ns.cv_folds)
        pipeline = build_pipeline(ns.model, categorical_cols, numeric_cols, seed=ns.seed + fold_idx)
        pipeline.fit(X.iloc[train_idx], y[train_idx])
        preds = pipeline.predict(X.iloc[test_idx])
        acc = accuracy_score(y[test_idx], preds)
        f1 = f1_score(y[test_idx], preds, average="macro")
        fold_metrics.append({"fold": fold_idx, "accuracy": acc, "macro_f1": f1})
        y_true.extend(y[test_idx])
        y_pred.extend(preds)

    overall_accuracy = accuracy_score(y_true, y_pred)
    overall_f1 = f1_score(y_true, y_pred, average="macro")

    LOGGER.info("CV accuracy=%.3f macro_f1=%.3f", overall_accuracy, overall_f1)

    final_pipeline = build_pipeline(ns.model, categorical_cols, numeric_cols, seed=ns.seed)
    final_pipeline.fit(X, y)

    feature_names = list(get_feature_names(final_pipeline))
    metrics_payload = {
        "model": ns.model,
        "timestamp_utc": datetime.utcnow().isoformat(),
        "accuracy": overall_accuracy,
        "macro_f1": overall_f1,
        "folds": fold_metrics,
    }
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    feature_list_path = output_dir / "feature_list.json"
    feature_list_path.write_text(json.dumps(feature_names, indent=2), encoding="utf-8")

    label_map_path = output_dir / "label_map.json"
    label_map_path.write_text(json.dumps(label_map, indent=2), encoding="utf-8")

    model_path = output_dir / "model.joblib"
    joblib.dump(final_pipeline, model_path)

    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(label_map))))
    class_labels = [label for label, _ in sorted(label_map.items(), key=lambda kv: kv[1])]
    save_confusion_matrix(report_dir / "confusion_matrix.png", cm, class_labels)

    model_step = final_pipeline.named_steps["model"]
    if hasattr(model_step, "feature_importances_"):
        importances = model_step.feature_importances_
        save_feature_importances(report_dir / "feature_importances.png", feature_names, importances)

    prepared_root = features_path.parent
    update_split_metadata(
        prepared_root,
        {
            "seed": ns.seed,
            "group_column": ns.group_col,
            "model": ns.model,
        },
    )

    LOGGER.info("Saved model artifacts to %s", output_dir)
    return 0


def get_feature_names(pipeline: Pipeline) -> List[str]:
    preprocess = pipeline.named_steps["preprocess"]
    try:
        names = preprocess.get_feature_names_out()
        return names.tolist()
    except AttributeError:  # pragma: no cover - fallback
        return [f"feature_{i}" for i in range(pipeline.named_steps["model"].n_features_in_)]


def main(argv: List[str] | None = None) -> int:
    ns = parse_args(argv)
    return run_training(ns)


if __name__ == "__main__":
    raise SystemExit(main())
