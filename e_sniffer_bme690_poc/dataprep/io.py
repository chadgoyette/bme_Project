from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from .schemas import RunMetadata

RAW_COLUMNS = [
    "timestamp_ms",
    "gas_resistance_ohms",
    "temperature_C",
    "humidity_pct",
    "pressure_Pa",
]


@dataclass
class RunData:
    run_dir: Path
    metadata: RunMetadata
    raw: pd.DataFrame


def discover_run_dirs(data_root: Path) -> List[Path]:
    runs: List[Path] = []
    if not data_root.exists():
        return runs
    for date_dir in sorted(p for p in data_root.iterdir() if p.is_dir()):
        for specimen_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
            for run_dir in sorted(p for p in specimen_dir.iterdir() if p.is_dir()):
                raw_path = run_dir / "raw.csv"
                meta_path = run_dir / "metadata.json"
                if raw_path.exists() and meta_path.exists():
                    runs.append(run_dir)
    return runs


def load_raw_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if list(df.columns) != RAW_COLUMNS:
        raise ValueError(f"Unexpected columns in {path}: {list(df.columns)}")
    return df


def load_metadata(path: Path) -> RunMetadata:
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return RunMetadata(**payload)


def load_run(run_dir: Path) -> RunData:
    metadata = load_metadata(run_dir / "metadata.json")
    raw = load_raw_csv(run_dir / "raw.csv")
    return RunData(run_dir=run_dir, metadata=metadata, raw=raw)
