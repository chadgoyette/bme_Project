# Workflow UI

The workflow application brings the `dataprep` and `training` CLIs into a single PySide6 window so you can kick off feature preparation and model training without dropping to the terminal.

## Usage

```bash
python -m workflow.app
```

### Data Preparation

1. Pick the raw run directory (`data_root`) and the output folder for prepared artefacts.
2. Adjust window size, stride, baseline, resample frequency, and maximum gap handling as needed.
3. Click **Run Data Prep** to launch `dataprep.build`. Logs from the CLI stream into the window while it runs.

When the process succeeds, the UI populates the training section with the new `features.parquet` path so you can move straight into model building.

### Training

1. Confirm the features parquet (auto-filled after prep) and choose an experiment output directory.
2. Select the estimator (`rf`, `logreg`, or `gbt`), grouped cross-validation column, fold count, and random seed.
3. Click **Run Training** to invoke `training.train`. Progress logs appear in the same log pane, and the status label updates when training finishes.

Both stages run in background `python -m` processes to keep the UI responsive. Output directories are created automatically, and the app refuses to overwrite a non-empty training experiment folder to avoid accidental data loss.
