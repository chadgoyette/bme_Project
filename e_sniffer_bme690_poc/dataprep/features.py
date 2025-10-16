from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .schemas import RunMetadata


def _slope_per_second(series: np.ndarray, sample_rate_hz: float) -> float:
    if len(series) < 2 or sample_rate_hz <= 0:
        return 0.0
    x = np.linspace(0, (len(series) - 1) / sample_rate_hz, num=len(series))
    slope, _ = np.polyfit(x, series, 1)
    return float(slope)


def _mean_abs_diff(series: np.ndarray) -> float:
    if len(series) < 2:
        return 0.0
    return float(np.mean(np.abs(np.diff(series))))


def _early_late_ratio(series: np.ndarray) -> float:
    if len(series) < 5:
        return 1.0
    quint = max(int(len(series) * 0.2), 1)
    early = float(np.mean(series[:quint]))
    late = float(np.mean(series[-quint:]))
    if late == 0:
        return 0.0
    return float(early / late)


def compute_window_features(
    window: pd.DataFrame,
    metadata: RunMetadata,
    sample_rate_hz: float,
) -> Dict[str, object]:
    gas = window["gas_resistance_ohms"].to_numpy(dtype=float)
    gas_delta = window["gas_delta"].to_numpy(dtype=float)
    temp = window["temperature_C"].to_numpy(dtype=float)
    humidity = window["humidity_pct"].to_numpy(dtype=float)

    features: Dict[str, object] = {
        "specimen_id": metadata.specimen_id,
        "run_id": metadata.run_id,
        "window_start_ms": int(window["timestamp_ms"].iloc[0]),
        "window_end_ms": int(window["timestamp_ms"].iloc[-1]),
        "quality_class": _quality_for_window(window),
        "freshness_label": metadata.label(),
        "meat_type": metadata.meat_type,
        "age_days": metadata.age_days,
    }

    def add_stats(prefix: str, series: np.ndarray) -> None:
        features[f"{prefix}_mean"] = float(np.mean(series))
        features[f"{prefix}_std"] = float(np.std(series, ddof=1)) if len(series) > 1 else 0.0
        features[f"{prefix}_min"] = float(np.min(series))
        features[f"{prefix}_max"] = float(np.max(series))
        features[f"{prefix}_slope_per_s"] = _slope_per_second(series, sample_rate_hz)
        features[f"{prefix}_mean_abs_diff"] = _mean_abs_diff(series)
        features[f"{prefix}_early_late_ratio"] = _early_late_ratio(series)

    add_stats("gas", gas)
    add_stats("gas_delta", gas_delta)

    features["temperature_mean"] = float(np.mean(temp))
    features["temperature_range"] = float(np.max(temp) - np.min(temp))
    features["humidity_mean"] = float(np.mean(humidity))
    features["humidity_range"] = float(np.max(humidity) - np.min(humidity))

    return features


def _quality_for_window(window: pd.DataFrame) -> str:
    if "gap_unfilled" in window and window["gap_unfilled"].any():
        return "gap"
    if "gap_filled" in window and window["gap_filled"].any():
        return "interpolated"
    return "clean"
