# Detector UI

The detector application drives the Bosch BME690 in real time, streams heater-profile readings through the trained classification pipeline, and highlights the most likely class with LED indicators. It shares the same feature engineering flow as `dataprep`, so the probabilities you see during a run line up with the metrics reported during training.

## Usage

```bash
python -m detector.app
```

1. **Load Model** – Choose the `model.joblib` exported by `training`. The detector loads `label_map.json` from the same folder to display human-readable class names.
2. **Load Metadata** – Select the `metadata.json` describing the specimen (the same schema used by `dataprep`). These fields keep downstream features consistent with what the model expects.
3. **Select Profile** – Pick one of the bundled heater profiles or load a `.bmeprofile` file that matches your sampling routine.
4. **Start** – The app warms the sensor, then cycles steps while plotting gas, temperature, and humidity. LEDs update with per-class confidence percentages whenever a window scores above zero.
5. **Stop** – Press *Stop* to halt gracefully. The detector writes a CSV of per-window probabilities under `logs/detector/` for later review or audit.

## Highlights

- Reuses `collector.runtime.CollectorRunner` for hardware control, ensuring the detector follows the same heater timing as the capture pipeline.
- Streams readings through the same 1 Hz resampling, baseline correction, and windowing strategy implemented in `dataprep`.
- Logs `window_start_ms`, `window_end_ms`, and class probabilities to support regression testing of new models.
- LED indicators provide an at-a-glance gut-check against known specimens before deployment.

Because the detector mirrors the training feature pipeline, it is ideal for validating fresh experiments: expose known samples, watch the LEDs, and confirm the probabilities align with expectations before shipping an update.
