# Live Test UI

The live test application replays or streams Bosch BME690 CSV data, computes the same window features as `dataprep`, and visualises per-class probabilities in real time.

## Modes

- **Replay**: Load an existing CSV and step through it at 1× speed (default for demos).
- **Tail**: Follow a Bosch DD CSV being generated on disk.
- **Subprocess**: Reserve for the Track B logger (stubbed, but interface ready).

## Key Features

- Loads `model.joblib` produced by `training`.
- Reuses `dataprep` feature engineering for strict parity.
- EMA smoothing toggle and hysteresis hold to reduce chatter.
- Logs all inferences to `inference_log.csv` beside the source file.

## Usage

```bash
python -m live_test.app
```

1. Pick a mode ("Replay CSV" to start).
2. Select the input CSV and corresponding `metadata.json`.
3. Load a trained `model.joblib`.
4. Press **Start** to stream and observe per-class probability bars.

The app writes an `inference_log.csv` with timestamped probabilities and the winning class.

## Detector Workflow

Load one or more experiments from `models/`, replay or stream an unknown sample, and inspect the class probabilities reported for each algorithm. Because the preprocessing logic is identical to `dataprep`, the detector honours the same baseline removal and window definitions recommended in electronic-nose literature [Li & Suslick, 2016](https://doi.org/10.1021/acssensors.6b00492); [Kodogiannis & Alshejari, 2025](https://doi.org/10.3390/s25103198). The exported `inference_log.csv` provides a persistent record that can be fed back into future training runs to expand the algorithm library.

## References

- Z. Li and K. S. Suslick, "Portable Optoelectronic Nose for Monitoring Meat Freshness," *ACS Sensors*, 2016, 1(11), 1330–1335. https://doi.org/10.1021/acssensors.6b00492
- H. T. Pham et al., "An IoT-Based Smart Electronic Nose System for Non-Destructive Meat Freshness Monitoring," *JST: Engineering and Technology for Sustainable Development*, 2024, 34(2), 31–39. https://doi.org/10.51316/jst.173.etsd.2024.34.2.5
- V. S. Kodogiannis and A. Alshejari, "Data Fusion of Electronic Nose and Multispectral Imaging for Meat Spoilage Detection Using Machine Learning Techniques," *Sensors*, 2025, 25(10), 3198. https://doi.org/10.3390/s25103198
