# Data Preparation CLI

`dataprep` converts raw Bosch Development Desktop (DD) exports into a tidy, windowed feature table for modelling. The process follows well-established electronic-nose workflows for meat freshness assessment that emphasise baseline drift removal, sliding-window summarisation, and preservation of the original raw signals for auditability [Li & Suslick, 2016](https://doi.org/10.1021/acssensors.6b00492); [Pham et al., 2024](https://doi.org/10.51316/jst.173.etsd.2024.34.2.5); [Kodogiannis & Alshejari, 2025](https://doi.org/10.3390/s25103198).

## Inputs and Raw Data Retention

Each run directory produced by `collector` contains:

- `bme690_<sample>_<timestamp>.csv` – raw BME690 readings (unchanged by dataprep).
- `metadata.json` – specimen identifiers, warm-up duration, and labels.

`dataprep` never edits or deletes these source files. All derived assets are written under `prepared/`, keeping the raw logs intact for future reprocessing or forensic analysis.

## Processing Workflow

1. **Load run folders** (CSV + metadata). Multiple runs can be processed in one invocation.
2. **Trim warm-up** seconds (metadata key `warmup_sec`). Discarding transient heating periods aligns with prior studies that emphasise steady-state gas responses for reliable classification [Li & Suslick, 2016].
3. **Resample to a uniform grid** (default 1 Hz) using time interpolation for gaps shorter than `--max-gap-sec` (default 3 s). Larger gaps are flagged in the `quality_class` column so downstream training can exclude them if desired.
4. **Baseline correction**: subtract the mean gas resistance recorded during the first `--baseline-sec` seconds after warm-up to mitigate long-term drift, a common strategy in electronic-nose deployments [Pham et al., 2024].
5. **Sliding windows**: construct fixed-length windows (`--window-sec`, default 600 s) with stride `--stride-sec` (default 60 s). Each window is tagged with specimen metadata and a freshness label (`fresh` vs. `aged`, overridable via metadata).
6. **Feature generation**: for `gas_resistance`, `gas_delta`, temperature, and humidity, compute mean, standard deviation, min, max, slope (per second), mean absolute difference, and early/late ratios. These statistics capture both absolute concentration changes and kinetics that have proven useful in e-nose based spoilage detection [Kodogiannis & Alshejari, 2025].
7. **Quality annotations**: windows inherit `quality_class ∈ {clean, interpolated, gap}` so that noisy segments can be filtered prior to training.
8. **Reports and logs**: produce HTML summaries (`reports/dataprep_summary.html`), structured logs (`logs/dataprep.log`), features (`features.parquet`), labels (`labels.csv`), and split metadata (`split.json`). All timestamps remain millisecond UTC integers.

## Usage

```bash
python -m dataprep.build \
  --data-root ./data \
  --out ./prepared \
  --window-sec 600 \
  --stride-sec 60 \
  --baseline-sec 60 \
  --resample-hz 1
```

The command scans `./data/<run_id>/` folders, writes the derived artefacts to `./prepared/`, and prints a summary of counts and any anomalous runs.

## Outputs

- `prepared/features.parquet` – per-window feature rows ready for model training.
- `prepared/labels.csv` – specimen-level labels and window quality metadata.
- `prepared/split.json` – provenance used for the most recent training run.
- `prepared/reports/dataprep_summary.html` – class balance and missing-data visuals.
- `prepared/logs/dataprep.log` – detailed processing trace.

> **Tip:** regenerate features whenever the window size, resampling rate, or baseline length changes. Past runs remain untouched, so multiple prepared versions can coexist under different subdirectories (e.g., `prepared/win600_stride60/`).

## References

- Z. Li and K. S. Suslick, "Portable Optoelectronic Nose for Monitoring Meat Freshness," *ACS Sensors*, 2016, 1(11), 1330–1335. https://doi.org/10.1021/acssensors.6b00492
- H. T. Pham et al., "An IoT-Based Smart Electronic Nose System for Non-Destructive Meat Freshness Monitoring," *JST: Engineering and Technology for Sustainable Development*, 2024, 34(2), 31–39. https://doi.org/10.51316/jst.173.etsd.2024.34.2.5
- V. S. Kodogiannis and A. Alshejari, "Data Fusion of Electronic Nose and Multispectral Imaging for Meat Spoilage Detection Using Machine Learning Techniques," *Sensors*, 2025, 25(10), 3198. https://doi.org/10.3390/s25103198
