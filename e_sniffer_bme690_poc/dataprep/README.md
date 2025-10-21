# Data Preparation CLI

`dataprep` works with the updated collector pipeline. It scans the CSV logs that `collector` writes, groups rows by heater cycle, and produces fixed-length tensors tuned for 1D convolutional networks. The goal is to keep the preprocessing lightweight—only the structure that is absolutely required for training is preserved, and no statistical feature engineering is performed.

## Inputs

- **Collector logs**: each run is a CSV named `bme690_<sample_name>_<timestamp>.csv`, usually inside the `logs/` directory (or a custom directory you picked when starting the run).
- **Inline labels**: the `sample_name` column encodes the labels captured during collection, e.g. `Coffee > Dunkin > Hazelnut > Yes > No`. The CLI parses this string to recover:
  - `category` – the first component (`Coffee` in the example).
  - `primary_label` – the second component when present (defaults to `category` if missing).
  - `target_label` – the last component (what the CNN will learn to predict).
  - `label_path` – the entire hierarchy joined with `" / "` for later regrouping.
- **Metadata**: other fields (`specimen_id`, `storage`, `profile_name`, etc.) are copied into the prepared index so you can trace tensors back to their origin.

The CSVs are read in place. Nothing is modified or deleted in the log directories.

## Processing Workflow

1. **Discover CSV files** under `--logs-root` that match `bme690_*.csv`.
2. **Load and filter** each file.
   - Optionally drop rows where `heater_heat_stable` is `False` (`--drop-unstable`).
   - Always drop rows without a gas reading.
3. **Group by `cycle_index`** and sort by `step_index` to rebuild the time series for each heater cycle.
4. **Validate step count**.
   - The first valid cycle determines `steps_per_cycle` (or supply `--expected-steps`).
   - Cycles with fewer/more steps or NaNs in feature columns are skipped to keep a consistent tensor shape.
5. **Assemble tensors**. Every surviving cycle becomes a `float32` array shaped `(steps_per_cycle, 5)` with columns:
   `["gas_resistance_ohm", "sensor_temperature_C", "sensor_humidity_RH", "pressure_Pa", "commanded_heater_temp_C"]`.
6. **Collect metadata** describing the cycle and its labels.
7. **Write outputs** (NumPy archive, metadata index, label map, summary JSON) into the `--out` directory.

## Usage

```powershell
python -m dataprep.build `
  --logs-root .\logs `
  --out .\prepared_cnn `
  --drop-unstable
```

Key options:

- `--logs-root` (default `logs/`): where to search for collector CSVs.
- `--out` (default `prepared/`): destination folder for prepared artefacts.
- `--expected-steps`: if your heater profile always yields a fixed number of steps, set it explicitly; otherwise it is inferred.
- `--drop-unstable`: ignore rows where the collector could not confirm heater stability before logging. Leave it off if you prefer to keep every sample.

## Outputs

All files live in the directory provided via `--out`.

- `sequences.npz`
  - `signals`: array shaped `(samples, steps_per_cycle, 5)` ready to feed into a CNN.
  - `labels`: integer array aligned with `signals`.
  - `feature_names`: ordered list of feature columns.
- `index.csv`
  - One row per cycle with metadata (`source_file`, `cycle_index`, `specimen_id`, `sample_name`, `target_label`, etc.) and the `label_index` column that aligns with `labels`.
- `label_map.json`
  - Mapping from `target_label` strings to integer IDs used in `labels`.
- `summary.json`
  - Counts of samples per class, the inferred `steps_per_cycle`, and the feature list.

These artefacts are sufficient for the 1D CNN training workflow. Downstream code can load `sequences.npz`, perform any normalisation/augmentation that the model requires, and rely on `index.csv` plus `label_map.json` for experiment tracking.

## Tips

- If you run multiple heater profiles with different numbers of steps, prepare them separately or set `--expected-steps` to enforce the layout you expect.
- The metadata index keeps the full `label_path`, so you can collapse labels (e.g. map `Coffee / Dunkin / Hazelnut / Yes / No` to a binary class) without re-running `dataprep`.
- Regenerate the prepared tensors whenever you log new data—the CLI is idempotent and will simply append new cycles to the output tensors.
