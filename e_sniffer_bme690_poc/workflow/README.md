# Workflow UI

The workflow window stitches together the command-line tools so you can launch data preparation (and, for now, the legacy model trainer) without leaving the desktop app.

## Usage

```bash
python -m workflow.app
```

### Data Preparation Panel

This section wraps the new `dataprep.build` that produces CNN-ready tensors.

- **Logs root** (folder) – the directory that contains your collector CSVs. The prep step searches recursively for files named `bme690_*.csv`. The raw logs are read-only; nothing is modified in place.
- **Output directory** (folder) – where the prepared artefacts land (`sequences.npz`, `index.csv`, `label_map.json`, `summary.json`). The folder is created if it does not exist.
- **Expected steps (0 = infer)** – optional heater-step count per cycle. Leave it at `0` to let `dataprep` infer the value from the first clean cycle, or set an explicit positive integer to enforce the layout.
- **Drop heater_unstable rows** – when enabled (default), the prep step discards any samples where `heater_heat_stable` was false before grouping cycles. Disable it if you want to keep every logged row.

Click **Run Data Prep** to start the background process. Console output streams into the log pane, and the status label flips to "completed" when tensors are ready. The completion message includes the path to the generated `sequences.npz`.

### Training Panel (Legacy)

The controls in this group still target the legacy tabular trainer (`training.train`) that expects a `features.parquet` file. Until the CNN trainer is wired into the app:

- **Features file** – must point to the legacy `features.parquet`. Selecting an `.npz` tensor archive will raise a warning.
- **Output directory** – destination folder for the trained model artefacts; the app refuses to run if the folder already contains files.
- **Model / Group column / CV folds / Random seed** – fed straight through to the scikit-learn based trainer (random forest, logistic regression, or gradient boosting). These settings are ignored by the future CNN workflow.

If you plan to train the new 1D convolutional network, launch the dedicated CNN training script (coming in a follow-up change) directly from the terminal once it lands. The workflow UI will be updated to drive that path when it is ready.

### General Notes

- Both stages run as `python -m …` subprocesses so the UI stays responsive.
- Prep and train outputs never overwrite existing files; choose a fresh folder for every experiment.
- The log pane keeps a full transcript of the subprocess output for later troubleshooting.
