from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run inference on a feature CSV using a trained model.")
    parser.add_argument("--model", type=Path, required=True, help="Path to model.joblib")
    parser.add_argument("--features", type=Path, required=True, help="CSV file with window-level features.")
    parser.add_argument("--label-map", type=Path, help="Optional label_map.json for decoding class indices.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model = joblib.load(args.model)
    df = pd.read_csv(args.features)
    proba = model.predict_proba(df)
    preds = proba.argmax(axis=1)

    inverse_labels = None
    if args.label_map and args.label_map.exists():
        label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
        inverse_labels = {int(idx): label for label, idx in label_map.items()}

    for idx, row in enumerate(proba):
        label = preds[idx]
        decoded = inverse_labels.get(int(label), str(label)) if inverse_labels else str(label)
        print(f"Sample {idx}: predicted={decoded} probs={row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
