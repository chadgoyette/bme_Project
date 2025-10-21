from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("dataprep")

FEATURE_COLUMNS: Tuple[str, ...] = (
    "gas_resistance_ohm",
    "sensor_temperature_C",
    "sensor_humidity_RH",
    "pressure_Pa",
    "commanded_heater_temp_C",
)


def parse_args(args: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert collector CSV logs into cycle tensors for 1D CNN training.")
    parser.add_argument(
        "--logs-root",
        type=Path,
        default=Path("logs"),
        help="Root directory that contains collector CSV files (searched recursively).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("prepared"),
        help="Directory where tensors, metadata, and summaries will be written.",
    )
    parser.add_argument(
        "--expected-steps",
        type=int,
        default=None,
        help="Optional number of heater steps per cycle. If omitted the value is inferred from the first valid cycle.",
    )
    parser.add_argument(
        "--drop-unstable",
        action="store_true",
        help="Discard rows where heater_heat_stable is False before grouping cycles.",
    )
    return parser.parse_args(args)


def discover_csv_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("bme690_*.csv") if p.is_file())


def extract_label_fields(sample_name: str) -> Dict[str, str]:
    parts = [part.strip() for part in sample_name.split(">") if part.strip()]
    if not parts:
        cleaned = sample_name.strip()
        return {
            "label_path": cleaned,
            "category": cleaned,
            "primary_label": cleaned,
            "target_label": cleaned,
        }
    label_path = " / ".join(parts)
    category = parts[0]
    primary_label = parts[1] if len(parts) > 1 else parts[0]
    target_label = parts[-1]
    return {
        "label_path": label_path,
        "category": category,
        "primary_label": primary_label,
        "target_label": target_label,
    }


def _stable_rows(df: pd.DataFrame, drop_unstable: bool) -> pd.DataFrame:
    if not drop_unstable:
        return df
    mask = df["heater_heat_stable"].fillna(False)
    return df.loc[mask].copy()


def build_cycle_samples(
    df: pd.DataFrame,
    source: Path,
    expected_steps: Optional[int],
    drop_unstable: bool,
) -> Tuple[List[np.ndarray], List[Dict[str, object]], Optional[int]]:
    if df.empty:
        LOGGER.warning("CSV %s produced no rows.", source)
        return [], [], expected_steps

    df = _stable_rows(df, drop_unstable)
    df = df.dropna(subset=["gas_resistance_ohm"])
    if df.empty:
        LOGGER.warning("CSV %s has no usable rows after filtering.", source)
        return [], [], expected_steps

    sequences: List[np.ndarray] = []
    metadata_rows: List[Dict[str, object]] = []
    inferred_steps = expected_steps

    grouped = df.groupby("cycle_index", sort=True)
    for cycle_idx, cycle_df in grouped:
        cycle_df = cycle_df.sort_values("step_index")
        if inferred_steps is None:
            inferred_steps = int(cycle_df.shape[0])
            LOGGER.debug("Inferred %s steps per cycle from %s", inferred_steps, source)
        if cycle_df.shape[0] != inferred_steps:
            LOGGER.info(
                "Skipping cycle %s in %s because step count %s != expected %s",
                cycle_idx,
                source,
                cycle_df.shape[0],
                inferred_steps,
            )
            continue
        if cycle_df[list(FEATURE_COLUMNS)].isna().any().any():
            LOGGER.info("Skipping cycle %s in %s due to NaN feature values.", cycle_idx, source)
            continue

        signal = cycle_df[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
        labels = extract_label_fields(str(cycle_df["sample_name"].iloc[0]))
        metadata = {
            "source_file": str(source),
            "cycle_index": int(cycle_idx),
            "specimen_id": str(cycle_df["specimen_id"].iloc[0]),
            "sample_name": str(cycle_df["sample_name"].iloc[0]),
            "profile_name": str(cycle_df["profile_name"].iloc[0]),
            "profile_hash": str(cycle_df["profile_hash"].iloc[0]),
            "storage": str(cycle_df["storage"].iloc[0]),
            "notes": str(cycle_df["notes"].iloc[0]),
        }
        metadata.update(labels)
        sequences.append(signal)
        metadata_rows.append(metadata)

    return sequences, metadata_rows, inferred_steps


def _stack_signals(signals: List[np.ndarray], expected_steps: int) -> np.ndarray:
    if not signals:
        return np.zeros((0, expected_steps, len(FEATURE_COLUMNS)), dtype=np.float32)
    return np.stack(signals, axis=0)


def _encode_labels(metadata_rows: Iterable[Dict[str, object]]) -> Tuple[np.ndarray, Dict[str, int]]:
    labels = [row["target_label"] for row in metadata_rows]
    unique = sorted(set(labels))
    mapping = {label: idx for idx, label in enumerate(unique)}
    encoded = np.array([mapping[label] for label in labels], dtype=np.int64)
    return encoded, mapping


def _write_outputs(
    out_root: Path,
    signals: np.ndarray,
    labels: np.ndarray,
    metadata_rows: List[Dict[str, object]],
    label_map: Dict[str, int],
) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    tensors_path = out_root / "sequences.npz"
    np.savez_compressed(
        tensors_path,
        signals=signals,
        labels=labels,
        feature_names=np.array(FEATURE_COLUMNS, dtype="U50"),
    )

    metadata_df = pd.DataFrame(metadata_rows)
    metadata_df["label_index"] = labels
    metadata_path = out_root / "index.csv"
    metadata_df.to_csv(metadata_path, index=False)

    label_map_path = out_root / "label_map.json"
    label_map_path.write_text(json.dumps(label_map, indent=2), encoding="utf-8")

    summary = {
        "samples": int(signals.shape[0]),
        "steps_per_cycle": int(signals.shape[1] if signals.size else 0),
        "feature_columns": list(FEATURE_COLUMNS),
        "label_counts": {label: int((labels == idx).sum()) for label, idx in label_map.items()},
    }
    summary_path = out_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ns = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    csv_files = discover_csv_files(ns.logs_root)
    if not csv_files:
        LOGGER.warning("No collector CSV files found under %s", ns.logs_root)

    expected_steps = ns.expected_steps
    all_signals: List[np.ndarray] = []
    all_metadata: List[Dict[str, object]] = []

    for csv_path in csv_files:
        LOGGER.info("Processing %s", csv_path)
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            LOGGER.error("Failed to read %s: %s", csv_path, exc)
            continue
        signals, metadata_rows, expected_steps = build_cycle_samples(
            df,
            csv_path,
            expected_steps,
            drop_unstable=ns.drop_unstable,
        )
        all_signals.extend(signals)
        all_metadata.extend(metadata_rows)

    if expected_steps is None:
        expected_steps = 0

    signal_tensor = _stack_signals(all_signals, expected_steps)
    if all_metadata:
        label_array, label_map = _encode_labels(all_metadata)
    else:
        label_array = np.zeros((0,), dtype=np.int64)
        label_map = {}

    _write_outputs(ns.out, signal_tensor, label_array, all_metadata, label_map)
    LOGGER.info("Wrote tensors and metadata to %s", ns.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
