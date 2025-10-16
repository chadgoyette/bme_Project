# Training Pipeline

The `training` package ingests the feature matrix produced by `dataprep`, performs grouped cross-validation, and exports a fully reproducible scikit-learn pipeline for downstream detection. The modelling approach aligns with best practices reported for electronic-nose meat monitoring, which stress rigorous cross-validation and transparency of feature importance [Li & Suslick, 2016](https://doi.org/10.1021/acssensors.6b00492); [Kodogiannis & Alshejari, 2025](https://doi.org/10.3390/s25103198).

## Inputs

- `prepared/features.parquet` – per-window features (`specimen_id`, engineered statistics, window timing).
- `prepared/labels.csv` – freshness labels and window quality tags (for analysis; not strictly required).
- `prepared/split.json` – automatically updated with the last training seed and grouping column for audit trails.

Raw collector CSV files remain untouched because the pipeline only reads the parquet output from `dataprep`.

## Usage

```bash
python -m training.train \
  --in ./prepared/features.parquet \
  --out ./models/exp_20250101_1200 \
  --group-col specimen_id \
  --model rf \
  --cv-folds 5 \
  --seed 42
```

Key parameters:

- `--group-col` ensures that all windows from the same specimen stay within a single fold (mitigating optimistic scores).
- `--model` chooses one of three baseline estimators (see below).
- `--cv-folds` controls grouped K-fold count (default 5).
- `--seed` drives both fold shuffling and final model training.

## Training Flow

1. Load features and parse the metadata columns required by the chosen group (`specimen_id` by default).
2. Split the data using `GroupKFold`, fit the chosen pipeline on each fold, and accumulate metrics (accuracy, macro F1).
3. Fit a final model on the full dataset using the same preprocessing steps.
4. Persist artefacts and update `prepared/split.json` so future runs can reproduce the exact configuration.

## Exported Artefacts

| File | Purpose |
| ---- | ------- |
| `model.joblib` | Complete `Pipeline` (preprocessing + estimator). Load this in `live_test` or other apps. |
| `metrics.json` | Overall accuracy, macro-F1, and per-fold scores. |
| `feature_list.json` | Ordered list of feature names after preprocessing (useful for feature explanations). |
| `label_map.json` | Mapping from string labels (e.g., `"fresh"`) to integer classes used internally. |
| `reports/confusion_matrix.png` | Confusion matrix summarising grouped CV predictions. |
| `reports/feature_importances.png` | Available for tree-based models (RF / GBT) to highlight driving features. |

Running the command also updates `prepared/split.json` with the seed, grouping column, and timestamp of the training run.

## Available Models

- `logreg` – Logistic Regression with standard scaling (strong baseline for linearly separable problems).
- `rf` – Random Forest (200 estimators, parallel inference).
- `gbt` – Gradient Boosted Trees (good for subtle, monotonic relationships).

Additional models can be added by extending `train.py` and the CLI choices.

## Using a Trained Model

1. Train the model and confirm metrics meet your acceptance criteria.
2. Copy the resulting `models/<experiment>` folder to the deployment machine.
3. In `live_test`, select the same `model.joblib` to stream predictions against new or replayed samples.
4. Retain `metrics.json` and `feature_list.json` alongside the model for traceability and to assist in detector explainability.

The detection program can evaluate unknown samples by loading each trained model in turn and reporting per-class confidence; combining multiple trained folders effectively produces an algorithm library.

## References

- Li, Z.; Suslick, K. S. *Portable Optoelectronic Nose for Monitoring Meat Freshness.* **ACS Sensors**, 2016, 1(11), 1330–1335. [https://doi.org/10.1021/acssensors.6b00492](https://doi.org/10.1021/acssensors.6b00492)
- Kodogiannis, V. S.; Alshejari, A. *Data Fusion of Electronic Nose and Multispectral Imaging for Meat Spoilage Detection Using Machine Learning Techniques.* **Sensors**, 2025, 25(10), 3198. [https://doi.org/10.3390/s25103198](https://doi.org/10.3390/s25103198)
