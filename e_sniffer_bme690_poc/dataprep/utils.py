from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Iterable, Iterator, Tuple

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


LOGGER = logging.getLogger("dataprep")


def drop_warmup(df: pd.DataFrame, warmup_sec: int) -> pd.DataFrame:
    if df.empty or warmup_sec <= 0:
        return df.copy()
    start_ts = int(df["timestamp_ms"].iloc[0])
    cutoff = start_ts + warmup_sec * 1000
    trimmed = df[df["timestamp_ms"] >= cutoff].copy()
    if trimmed.empty:
        LOGGER.warning("All data trimmed by warmup (cutoff=%s)", cutoff)
    return trimmed


def resample_uniform(
    df: pd.DataFrame, target_hz: float, max_gap_sec: float = 3.0
) -> Tuple[pd.DataFrame, pd.Series]:
    if df.empty:
        return df.copy(), pd.Series(dtype=bool)
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms")
    df.set_index("timestamp", inplace=True)
    freq_ms = int(round(1000 / target_hz))
    timeline = pd.date_range(df.index.min(), df.index.max(), freq=f"{freq_ms}ms")
    resampled = df.reindex(timeline)
    missing_before = resampled["gas_resistance_ohms"].isna()
    limit = int(np.floor(max_gap_sec * target_hz))
    resampled = resampled.interpolate(
        method="time",
        limit=limit if limit > 0 else None,
        limit_direction="both",
    )
    missing_after = resampled["gas_resistance_ohms"].isna()
    resampled["timestamp_ms"] = (resampled.index.view("int64") // 1_000_000).astype("int64")
    resampled.reset_index(drop=True, inplace=True)
    resampled["gap_filled"] = (~missing_after) & missing_before
    resampled["gap_unfilled"] = missing_after
    quality_mask = resampled["gap_unfilled"]
    return resampled, quality_mask


def baseline_correct(df: pd.DataFrame, baseline_sec: int) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        df["gas_delta"] = 0.0
        return df
    start_ts = int(df["timestamp_ms"].iloc[0])
    cutoff = start_ts + baseline_sec * 1000
    baseline_region = df[df["timestamp_ms"] <= cutoff]
    if baseline_region.empty:
        baseline_value = df["gas_resistance_ohms"].iloc[0]
    else:
        baseline_value = baseline_region["gas_resistance_ohms"].mean()
    df["gas_delta"] = df["gas_resistance_ohms"] - baseline_value
    return df


def sliding_windows(
    df: pd.DataFrame, window_sec: int, stride_sec: int, sample_rate_hz: float
) -> Iterator[pd.DataFrame]:
    if df.empty:
        return iter(())
    step = int(round(stride_sec * sample_rate_hz))
    size = int(round(window_sec * sample_rate_hz))
    if size <= 0 or step <= 0:
        raise ValueError("Window and stride must be positive")
    total = df.shape[0]
    for start in range(0, max(total - size + 1, 0), step):
        stop = start + size
        window = df.iloc[start:stop].copy()
        if window.shape[0] == size:
            yield window


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_summary_html(out_path: Path, features: pd.DataFrame, labels: pd.DataFrame) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if features.empty:
        summary_html = "<html><body><h1>DataPrep Summary</h1><p>No features generated.</p></body></html>"
        out_path.write_text(summary_html, encoding="utf-8")
        return out_path

    # Class balance
    if "quality_class" in labels.columns:
        class_counts = labels["quality_class"].value_counts()
    else:
        class_counts = features.get("quality_class", pd.Series(dtype=int)).value_counts()
    fig1, ax1 = plt.subplots(figsize=(3, 3))
    class_counts.plot(kind="bar", ax=ax1, color="#4C72B0")
    ax1.set_title("Quality Class Counts")
    ax1.set_xlabel("Quality Class")
    ax1.set_ylabel("Windows")
    class_counts_png = _fig_to_base64(fig1)

    # Feature coverage heatmap
    missing = features.isna().mean().sort_values(ascending=False).head(20)
    fig2, ax2 = plt.subplots(figsize=(4, 3))
    missing.plot(kind="barh", ax=ax2, color="#C44E52")
    ax2.set_title("Top Feature Missing Rates")
    ax2.set_xlabel("Missing Fraction")
    ax2.set_ylabel("Feature")
    missing_png = _fig_to_base64(fig2)

    html = f"""
    <html>
    <head><title>E-Sniffer DataPrep Summary</title></head>
    <body>
      <h1>E-Sniffer DataPrep Summary</h1>
      <p>Total windows: {len(features)}</p>
      <h2>Quality Class Distribution</h2>
      <img src="data:image/png;base64,{class_counts_png}" alt="Class Counts"/>
      <h2>Missing Rates (Top 20)</h2>
      <img src="data:image/png;base64,{missing_png}" alt="Missing Rates"/>
    </body>
    </html>
    """
    out_path.write_text(html, encoding="utf-8")
    return out_path
