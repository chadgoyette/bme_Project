from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List

import pandas as pd

from .features import compute_window_features
from .io import RunData, discover_run_dirs, load_run
from .utils import (
    baseline_correct,
    build_summary_html,
    drop_warmup,
    resample_uniform,
    setup_logging,
    sliding_windows,
)

LOGGER = logging.getLogger("dataprep")


def parse_args(args: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Bosch BME690 runs for training.")
    parser.add_argument("--data-root", type=Path, default=Path("data"), help="Root directory containing run folders.")
    parser.add_argument("--out", type=Path, default=Path("prepared"), help="Output directory for features and reports.")
    parser.add_argument("--window-sec", type=int, default=600, help="Window size in seconds.")
    parser.add_argument("--stride-sec", type=int, default=60, help="Stride between windows in seconds.")
    parser.add_argument("--baseline-sec", type=int, default=60, help="Duration used to compute gas baseline.")
    parser.add_argument("--resample-hz", type=float, default=1.0, help="Target resample frequency (Hz).")
    parser.add_argument("--max-gap-sec", type=float, default=3.0, help="Maximum gap length to interpolate (seconds).")
    return parser.parse_args(args)


def process_run(
    run: RunData,
    window_sec: int,
    stride_sec: int,
    baseline_sec: int,
    resample_hz: float,
    max_gap_sec: float,
) -> pd.DataFrame:
    LOGGER.info("Processing run %s / %s", run.metadata.specimen_id, run.metadata.run_id)
    df = drop_warmup(run.raw, run.metadata.warmup_sec)
    if df.empty:
        LOGGER.warning("Run %s produced no data after warmup trim", run.run_dir)
        return pd.DataFrame()
    df_resampled, _ = resample_uniform(df, target_hz=resample_hz, max_gap_sec=max_gap_sec)
    df_resampled = baseline_correct(df_resampled, baseline_sec=baseline_sec)
    windows = []
    for window in sliding_windows(df_resampled, window_sec=window_sec, stride_sec=stride_sec, sample_rate_hz=resample_hz):
        features = compute_window_features(window, metadata=run.metadata, sample_rate_hz=resample_hz)
        windows.append(features)
    if not windows:
        LOGGER.warning("Run %s produced no windows", run.run_dir)
        return pd.DataFrame()
    return pd.DataFrame(windows)


def main(argv: List[str] | None = None) -> int:
    ns = parse_args(argv)
    out_root: Path = ns.out
    features_path = out_root / "features.parquet"
    labels_path = out_root / "labels.csv"
    split_path = out_root / "split.json"
    report_path = out_root / "reports" / "dataprep_summary.html"
    log_path = out_root / "logs" / "dataprep.log"

    out_root.mkdir(parents=True, exist_ok=True)
    setup_logging(log_path)

    run_dirs = discover_run_dirs(ns.data_root)
    if not run_dirs:
        LOGGER.warning("No runs found in %s", ns.data_root)

    feature_frames: List[pd.DataFrame] = []
    for run_dir in run_dirs:
        run = load_run(run_dir)
        frame = process_run(
            run,
            window_sec=ns.window_sec,
            stride_sec=ns.stride_sec,
            baseline_sec=ns.baseline_sec,
            resample_hz=ns.resample_hz,
            max_gap_sec=ns.max_gap_sec,
        )
        if not frame.empty:
            feature_frames.append(frame)

    if feature_frames:
        features_df = pd.concat(feature_frames, ignore_index=True)
    else:
        features_df = pd.DataFrame()

    if features_df.empty:
        LOGGER.warning("No features generated; writing empty artifacts.")
        features_df.to_parquet(features_path, index=False)
        labels_df = pd.DataFrame(columns=["specimen_id", "run_id", "window_start_ms", "window_end_ms", "freshness_label", "quality_class"])
        labels_df.to_csv(labels_path, index=False)
        split_path.write_text(json.dumps({"groups": [], "seed": None}), encoding="utf-8")
        build_summary_html(report_path, features_df, labels_df)
        return 0

    features_df.to_parquet(features_path, index=False)

    labels_df = features_df[
        ["specimen_id", "run_id", "window_start_ms", "window_end_ms", "freshness_label", "quality_class"]
    ].copy()
    labels_df.to_csv(labels_path, index=False)

    split_payload = {
        "seed": 1234,
        "group_column": "specimen_id",
        "runs": sorted(features_df["run_id"].unique().tolist()),
    }
    split_path.write_text(json.dumps(split_payload, indent=2), encoding="utf-8")

    build_summary_html(report_path, features_df, labels_df)

    LOGGER.info("Wrote features to %s", features_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
