from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from dataprep.features import compute_window_features
from dataprep.schemas import RunMetadata

RAW_COLUMNS = [
    "timestamp_ms",
    "gas_resistance_ohms",
    "temperature_C",
    "humidity_pct",
    "pressure_Pa",
]


@dataclass
class FeatureConfig:
    window_sec: int
    stride_sec: int
    baseline_sec: int
    sample_rate_hz: float


class RealTimeFeatureExtractor:
    """Maintains a rolling buffer and emits dataprep-equivalent features."""

    def __init__(self, metadata: Dict[str, object], config: FeatureConfig) -> None:
        self.metadata = RunMetadata(**metadata)
        self.config = config
        self.window_samples = int(round(config.window_sec * config.sample_rate_hz))
        self.stride_samples = int(round(config.stride_sec * config.sample_rate_hz))
        self.baseline_samples = int(round(config.baseline_sec * config.sample_rate_hz))
        self._buffer = pd.DataFrame(columns=RAW_COLUMNS)
        self._baseline_value: Optional[float] = None
        self._next_start = 0

    def ingest(self, chunk: pd.DataFrame) -> List[Dict[str, object]]:
        if chunk.empty:
            return []
        missing_cols = [col for col in RAW_COLUMNS if col not in chunk.columns]
        if missing_cols:
            raise ValueError(f"Chunk missing columns: {missing_cols}")
        if self._buffer.empty:
            self._buffer = chunk.reset_index(drop=True)
        else:
            self._buffer = pd.concat([self._buffer, chunk], ignore_index=True)
        features: List[Dict[str, object]] = []
        if self._baseline_value is None and len(self._buffer) >= self.baseline_samples > 0:
            baseline_region = self._buffer.iloc[: self.baseline_samples]
            self._baseline_value = baseline_region["gas_resistance_ohms"].mean()
        if self._baseline_value is not None:
            self._buffer["gas_delta"] = self._buffer["gas_resistance_ohms"] - self._baseline_value
        else:
            self._buffer["gas_delta"] = 0.0
        self._buffer["gap_filled"] = False
        self._buffer["gap_unfilled"] = False

        while self._next_start + self.window_samples <= len(self._buffer):
            window = self._buffer.iloc[self._next_start : self._next_start + self.window_samples].copy()
            feat = compute_window_features(window, self.metadata, sample_rate_hz=self.config.sample_rate_hz)
            features.append(feat)
            self._next_start += self.stride_samples

        # Trim buffer to keep only necessary data.
        min_index = max(0, self._next_start - self.stride_samples)
        if min_index > 0:
            self._buffer = self._buffer.iloc[min_index:].reset_index(drop=True)
            self._next_start -= min_index
        return features


class ProbabilitySmoother:
    """EMA smoothing with hysteresis hold to avoid flickering class predictions."""

    def __init__(self, alpha: float, hold_seconds: int, threshold: float, sample_rate_hz: float) -> None:
        self.alpha = alpha
        self.hold_samples = max(1, int(round(hold_seconds * sample_rate_hz)))
        self.threshold = threshold
        self._ema: Optional[np.ndarray] = None
        self._current_label: Optional[int] = None
        self._pending_label: Optional[int] = None
        self._pending_count = 0

    def update(self, probs: np.ndarray) -> Tuple[np.ndarray, Optional[int]]:
        if self._ema is None:
            self._ema = probs.astype(float)
        else:
            self._ema = self.alpha * probs + (1.0 - self.alpha) * self._ema

        winner = int(np.argmax(probs))
        winner_prob = float(probs[winner])
        if winner_prob >= self.threshold:
            if self._current_label is None:
                self._current_label = winner
                self._pending_label = None
                self._pending_count = 0
                return self._ema.copy(), self._current_label
            if self._current_label == winner:
                self._pending_label = None
                self._pending_count = 0
            else:
                if self._pending_label == winner:
                    self._pending_count += 1
                else:
                    self._pending_label = winner
                    self._pending_count = 1
                if self._pending_count >= self.hold_samples:
                    self._current_label = winner
                    self._pending_label = None
                    self._pending_count = 0
        else:
            self._pending_label = None
            self._pending_count = 0
        return self._ema.copy(), self._current_label
