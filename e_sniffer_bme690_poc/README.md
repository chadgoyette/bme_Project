# E-Sniffer BME690 Proof of Concept

The `e_sniffer_bme690_poc` repository hosts a small-but-complete proof of concept for classifying meat freshness using a Bosch BME690 gas sensor. Four Python applications plus a Track B C logger cooperate to ingest raw Bosch Development Desktop (DD) CSV exports, prepare train-ready features, train models, and replay predictions live.

```
[collector] -> [dataprep] -> [training_cnn] -> [live_test]
     raw runs      sequences.npz      CNN model artefacts      live inference

Optional Track B logger (C) can stream raw CSV directly into collector/dataprep.
```

## Repository Layout

| Path | Purpose |
| ---- | ------- |
| `collector/` | PySide6 GUI that wraps Bosch DD logging, stores metadata, and produces quick QC outputs. |
| `dataprep/` | CLI that validates raw runs, trims warm-up, and converts cycles into fixed-length tensors (`sequences.npz`, metadata, summaries). |
| `training/` | Legacy CLI that performs grouped cross-validation on tabular features and exports serialized scikit-learn pipelines plus reports. |
| `training_cnn/` | PyTorch CLI that consumes `prepared/` tensors, trains a 1D convolutional model, and writes checkpoints/metrics. |
| `live_test/` | PySide6 GUI to replay or stream CSV data, compute rolling features, and display class probabilities with smoothing. |
| `detector/` | PySide6 GUI that drives the sensor directly, streams heater profile data, and flags known classes with LED indicators. |
| `workflow/` | PySide6 GUI that orchestrates data preparation and training in one place, wrapping the CLI stages. |
| `track_b/logger/` | COINES-based logger skeleton in C with CMake build files. |

Generated artefacts live under `data/`, `prepared/`, and `models/` (ignored by Git). Raw CSV logs written by `collector` are never modified; every downstream stage writes new files alongside them so that historical acquisitions remain available for reprocessing or forensic inspection.

## Scientific Context

The design choices mirror published electronic-nose research on meat spoilage, which emphasise (i) discarding heater warm-up intervals, (ii) extracting windowed statistics that capture both absolute gas resistance and its temporal kinetics, and (iii) validating models at the specimen level to avoid optimistic scores [Li & Suslick, 2016](https://doi.org/10.1021/acssensors.6b00492); [Pham et al., 2024](https://doi.org/10.51316/jst.173.etsd.2024.34.2.5); [Kodogiannis & Alshejari, 2025](https://doi.org/10.3390/s25103198). Each submodule README explains how the codebase operationalises these principles while keeping the raw signals intact.

## Quickstart

1. **Install dependencies**
   ```bash
   python -m venv .venv
   .venv/Scripts/Activate.ps1  # PowerShell
   pip install -r requirements.txt
   ```

2. **Collector UI**  
   ```bash
   make collector
   ```
   Manage heater profiles, enter specimen metadata, and press *Start* to warm the BME690 and log readings to `logs/<date>/bme690_<sample>_<timestamp>.csv`.

3. **Data Preparation (tensors)**
   ```bash
   make dataprep
   ```
   Converts collector logs into fixed-length cycle tensors (`sequences.npz`), per-cycle metadata (`index.csv`), and `summary.json` under `prepared/`.

4. **CNN Training**
   ```bash
   make train
   ```
   Trains the 1D convolutional network, saving `model.pt`, `metrics.json`, and `training_curves.png` into `models/cnn_<timestamp>/`.

5. **Workflow UI (prep + train)**
   ```bash
   make workflow
   ```
   Launch the combined orchestration UI to pick a data set, tweak prep parameters, and kick off either CNN or legacy training without shell commands.

6. **Live Test UI**
   ```bash
   make live
   ```
   Stream from a CSV tail or replay recorded data while visualising per-class probabilities for recorded acquisitions.

7. **Detector UI**
   ```bash
   make detector
   ```
   Run a live classification session directly against the sensor. Select a heater profile, metadata JSON, and trained model to watch per-class LEDs illuminate in real time while the gas/temperature/humidity traces update each profile step.

8. **Track B Logger (optional)**
   ```bash
   cmake -S track_b/logger -B track_b/logger/build
   cmake --build track_b/logger/build
   ```

## Data Flow

1. **collector** logs raw CSV, stores metadata (specimen ID, warm-up duration, profile hash), and produces quick QC captures.
2. **dataprep** ingests run folders, trims warm-up periods, and emits uniform-length cycle tensors plus metadata under `prepared/`.
3. **training_cnn** consumes the prepared tensors, fits the 1D convolutional network, and writes model artefacts to `models/cnn_<timestamp>/` together with metrics and training curves.
4. **live_test** (or any detector) loads one or more trained pipelines and evaluates unknown samples, logging class probabilities for later review.

## Development Notes

- Python 3.10+ is required. PySide6 is used for GUI applications.
- Timestamp handling is always millisecond UTC integers (`timestamp_ms`).
- Synthetic fixtures and simulators are provided to enable offline development without hardware.
- Run `pytest` at the repository root to execute all unit tests.

## References

- Z. Li and K. S. Suslick, "Portable Optoelectronic Nose for Monitoring Meat Freshness," *ACS Sensors*, 2016, 1(11), 1330–1335. https://doi.org/10.1021/acssensors.6b00492
- H. T. Pham et al., "An IoT-Based Smart Electronic Nose System for Non-Destructive Meat Freshness Monitoring," *JST: Engineering and Technology for Sustainable Development*, 2024, 34(2), 31–39. https://doi.org/10.51316/jst.173.etsd.2024.34.2.5
- V. S. Kodogiannis and A. Alshejari, "Data Fusion of Electronic Nose and Multispectral Imaging for Meat Spoilage Detection Using Machine Learning Techniques," *Sensors*, 2025, 25(10), 3198. https://doi.org/10.3390/s25103198
