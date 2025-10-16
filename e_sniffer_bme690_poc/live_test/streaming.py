from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

RAW_COLUMNS = [
    "timestamp_ms",
    "gas_resistance_ohms",
    "temperature_C",
    "humidity_pct",
    "pressure_Pa",
]


class ReplayCSVSource:
    """Replay a static CSV file at caller-controlled pace."""

    def __init__(self, path: Path, step_samples: int = 1) -> None:
        self.path = Path(path)
        self.step_samples = step_samples
        self._data = pd.read_csv(self.path)
        if list(self._data.columns) != RAW_COLUMNS:
            raise ValueError(f"Unexpected columns in {self.path}")
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def next_chunk(self) -> pd.DataFrame:
        if self._cursor >= len(self._data):
            return pd.DataFrame(columns=RAW_COLUMNS)
        next_cursor = min(self._cursor + self.step_samples, len(self._data))
        chunk = self._data.iloc[self._cursor:next_cursor].copy()
        self._cursor = next_cursor
        return chunk.reset_index(drop=True)


class TailCSVSource:
    """Tail a growing CSV file, returning only newly written rows."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._last_row_count = 0
        self._validate()

    def _validate(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        df = pd.read_csv(self.path)
        if list(df.columns) != RAW_COLUMNS:
            raise ValueError(f"Unexpected columns in {self.path}")
        self._last_row_count = df.shape[0]

    def next_chunk(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        new = df.iloc[self._last_row_count :].copy()
        self._last_row_count = df.shape[0]
        return new.reset_index(drop=True)


class SubprocessSource:
    """Placeholder for Track B logger integration."""

    def __init__(self, command: list[str]) -> None:
        self.command = command
        self._buffer = pd.DataFrame(columns=RAW_COLUMNS)

    def next_chunk(self) -> pd.DataFrame:
        # TODO: implement subprocess streaming after logger is available.
        return pd.DataFrame(columns=RAW_COLUMNS)
